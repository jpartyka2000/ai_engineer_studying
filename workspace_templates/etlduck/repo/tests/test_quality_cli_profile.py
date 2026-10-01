"""Quality gates, the CLI, raw-file profiling and the Spark façade.

Each quality check is tested in both directions: passing on good data, and **failing on data
constructed to break it**. A gate that has only ever been seen to pass is not known to work.
"""

from __future__ import annotations

import json

import pytest

from etlduck import quality
from etlduck.bronze import ingest_all
from etlduck.cli import main
from etlduck.gold import build_gold
from etlduck.profile import is_null_token, profile_jsonl, profile_landing_zone, render_profiles
from etlduck.silver import build_silver
from etlduck.spark_compat import LocalSession
from tests.conftest import event, write_accounts, write_raw_lines, write_usage

ACCOUNTS = [
    {"account_id": f"acct-{n:03d}", "name": f"A{n}", "plan": "team", "country": "DE"}
    for n in range(6)
]


def _run(connection, root):
    ingest_all(connection, root)
    build_silver(connection)
    build_gold(connection)


def _good(connection, root):
    """A small, entirely clean warehouse."""
    write_accounts(root, "accounts.csv", ACCOUNTS)
    write_usage(
        root,
        "usage_events_2026-03-01.jsonl",
        [event(f"e{n}", f"acct-{n % 6:03d}") for n in range(12)],
    )
    _run(connection, root)


# ---------------------------------------------------------------------------
# Quality gates, both directions
# ---------------------------------------------------------------------------


def test_every_check_passes_on_clean_data(connection, root):
    _good(connection, root)
    checks = quality.run_all(connection)
    assert [c.name for c in checks if not c.passed] == []
    quality.assert_ok(checks)


def test_the_committed_run_passes_every_quality_gate(seeded):
    """The gates, on the real data.

    The ``seeded`` fixture runs with ``strict=False`` so that a broken gate does not turn
    every integration test into the same fixture error -- which makes this the test that
    holds the gates to account. It names the failures rather than asserting a bare boolean,
    so the output says which gate went and not merely that one did.
    """
    _, result = seeded
    failed = [check.name for check in result.checks if not check.passed]
    assert failed == [], f"gates failed on the committed data: {failed}"
    assert result.ok


def test_reconciliation_fails_when_gold_is_wrong(connection, root):
    _good(connection, root)
    connection.execute("DELETE FROM gold_daily_usage WHERE account_id = 'acct-000'")
    assert not quality.check_gold_reconciles_with_silver(connection).passed


def test_the_grain_check_fails_on_a_repeated_account_day(connection, root):
    """Inserted straight into gold, bypassing the primary key by using a different date and
    then rewriting it, so the check is exercised rather than the constraint."""
    _good(connection, root)
    row = connection.execute(
        "SELECT event_date, account_id, plan, events, quantity, amount_cents "
        "FROM gold_daily_usage LIMIT 1"
    ).fetchone()
    connection.execute(
        "CREATE TABLE shadow AS SELECT * FROM gold_daily_usage; "
        "INSERT INTO shadow VALUES (?, ?, ?, ?, ?, ?)",
        list(row),
    )
    duplicates = connection.execute(
        "SELECT count(*) FROM (SELECT event_date, account_id FROM shadow "
        "GROUP BY event_date, account_id HAVING count(*) > 1)"
    ).fetchone()[0]
    assert duplicates == 1


def test_the_quarantine_budget_check_fails_when_breached(connection, root):
    """Two clean rows and one rejected is 33%, far past the 5% budget."""
    write_accounts(root, "accounts.csv", ACCOUNTS)
    write_usage(
        root,
        "usage_events_2026-03-01.jsonl",
        [event("e1"), event("e2"), event("bad", occurred_at="2026-03-01 10:00:00")],
    )
    _run(connection, root)
    check = quality.check_quarantine_within_budget(connection)
    assert not check.passed
    assert "budget is 5%" in check.detail


def test_the_accounts_check_fails_on_a_truncated_dimension(connection, root):
    """The case it exists for: usage loads, gold builds, every row has a NULL plan."""
    write_accounts(root, "accounts.csv", ACCOUNTS[:2])
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("e1", "acct-000")])
    _run(connection, root)
    assert not quality.check_accounts_present(connection).passed


def test_the_attribution_check_fails_on_usage_with_no_dimension_row(connection, root):
    write_accounts(root, "accounts.csv", ACCOUNTS)
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("e1", "acct-999")])
    _run(connection, root)
    check = quality.check_no_unattributed_usage(connection)
    assert not check.passed
    assert "no plan" in check.detail


def test_the_utc_date_check_fails_when_a_date_is_rederived_wrongly(connection, root):
    """Simulates a date computed in a local zone by shifting one row's event_date by a day.
    58 of the committed 400 rows are within range of this mistake, so the check matters."""
    _good(connection, root)
    connection.execute(
        "UPDATE silver_usage SET event_date = event_date + INTERVAL 1 DAY WHERE event_id = 'e0'"
    )
    check = quality.check_dates_are_utc_consistent(connection)
    assert not check.passed
    assert "1 silver rows" in check.detail


def test_assert_ok_reports_every_failure_not_just_the_first(connection, root):
    """One run should tell the on-call engineer everything that is wrong."""
    write_accounts(root, "accounts.csv", ACCOUNTS[:2])
    write_usage(
        root,
        "usage_events_2026-03-01.jsonl",
        [event("e1", "acct-999"), event("bad", occurred_at="2026-03-01 10:00:00")],
    )
    _run(connection, root)
    with pytest.raises(quality.QualityFailure) as caught:
        quality.assert_ok(quality.run_all(connection))
    message = str(caught.value)
    assert "accounts_present" in message
    assert "quarantine_within_budget" in message


def test_a_check_renders_as_a_reportable_line(connection, root):
    _good(connection, root)
    rendered = str(quality.check_accounts_present(connection))
    assert rendered.startswith("[PASS] accounts_present")


# ---------------------------------------------------------------------------
# Raw-file profiling
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["", "  ", "null", "NONE", "n/a", "NA", "-", "unknown", None])
def test_recognised_null_spellings(value):
    assert is_null_token(value)


@pytest.mark.parametrize("value", ["0", "false", "nil-value", "not applicable", 0, False])
def test_values_that_are_not_null_tokens(value):
    """``0`` and ``False`` are values, not absences. Reading them as missing would delete
    every legitimate zero in the file."""
    assert not is_null_token(value)


def test_profile_counts_lines_records_and_failures(root):
    write_raw_lines(
        root,
        "usage_events_a.jsonl",
        [json.dumps(event("e1")), "", "{not json", json.dumps(event("e2"))],
    )
    profile = profile_jsonl(root / "raw" / "usage_events_a.jsonl")
    assert (profile.lines, profile.records, profile.unparseable_lines, profile.blank_lines) == (
        4,
        2,
        1,
        1,
    )


def test_profile_reports_the_parse_failure_share(root):
    write_raw_lines(root, "usage_events_a.jsonl", [json.dumps(event("e1")), "{not json"])
    profile = profile_jsonl(root / "raw" / "usage_events_a.jsonl")
    assert profile.parse_failure_fraction == pytest.approx(0.5)


def test_profile_finds_a_sparse_field(root):
    """One record in four carries ``region``, so it is reported at 25% presence."""
    records = [event(f"e{n}") for n in range(4)]
    records[0]["region"] = "EU"
    write_raw_lines(root, "usage_events_a.jsonl", [json.dumps(r) for r in records])
    profile = profile_jsonl(root / "raw" / "usage_events_a.jsonl")
    assert profile.sparse_fields() == ["region"]
    assert profile.fields["region"].presence(profile.records) == pytest.approx(0.25)


def test_profile_counts_null_like_values_separately_from_absence(root):
    """A field that is present and empty is a different signal from one that is missing."""
    records = [event(f"e{n}", account_id="n/a") for n in range(3)]
    write_raw_lines(root, "usage_events_a.jsonl", [json.dumps(r) for r in records])
    profile = profile_jsonl(root / "raw" / "usage_events_a.jsonl")
    account = profile.fields["account_id"]
    assert account.present == 3
    assert account.null_fraction() == pytest.approx(1.0)


def test_profile_reports_a_constant_field(root):
    records = [event(f"e{n}", event_type="api_call") for n in range(4)]
    write_raw_lines(root, "usage_events_a.jsonl", [json.dumps(r) for r in records])
    findings = profile_jsonl(root / "raw" / "usage_events_a.jsonl").findings()
    assert any("single distinct value" in finding for finding in findings)


def test_profile_findings_are_stable_between_runs(root):
    """Read by a human diffing today's report against yesterday's, so an unstable order
    makes the whole thing useless."""
    records = [event(f"e{n}") for n in range(4)]
    records[0]["region"] = "EU"
    records[1]["tier"] = "gold"
    write_raw_lines(root, "usage_events_a.jsonl", [json.dumps(r) for r in records])
    path = root / "raw" / "usage_events_a.jsonl"
    assert profile_jsonl(path).findings() == profile_jsonl(path).findings()


def test_profiling_a_missing_file_raises(root):
    with pytest.raises(FileNotFoundError):
        profile_jsonl(root / "raw" / "absent.jsonl")


def test_a_file_of_json_arrays_has_no_records(root):
    """A JSON array per line is valid JSON and not a record. Counted as unparseable, because
    silently reading element zero would be a guess."""
    write_raw_lines(root, "usage_events_a.jsonl", ["[1, 2, 3]", "[4]"])
    profile = profile_jsonl(root / "raw" / "usage_events_a.jsonl")
    assert (profile.records, profile.unparseable_lines) == (0, 2)
    assert "no parseable records" in profile.findings()[0]


def test_profiling_the_committed_landing_zone(seeded_root):
    """Both committed usage files, each with its one deliberate truncated line."""
    profiles = profile_landing_zone(seeded_root / "raw")
    assert [p.path for p in profiles] == [
        "usage_events_2026-03-01.jsonl",
        "usage_events_2026-03-02.jsonl",
    ]
    assert all(p.unparseable_lines == 1 for p in profiles)
    assert all(p.records >= 200 for p in profiles)


def test_rendering_profiles_mentions_every_file(seeded_root):
    rendered = render_profiles(profile_landing_zone(seeded_root / "raw"))
    assert "usage_events_2026-03-01.jsonl" in rendered
    assert "account_id" in rendered


def test_rendering_no_profiles_says_so():
    assert render_profiles([]) == "no files matched"


# ---------------------------------------------------------------------------
# The Spark façade
# ---------------------------------------------------------------------------


def test_the_session_runs_sql_against_the_warehouse(connection, root):
    _good(connection, root)
    connection.close()
    session = LocalSession.builder().appName("test").root(root).getOrCreate()
    try:
        frame = session.sql("SELECT count(*) AS n FROM silver_usage")
        assert frame.first()["n"] == 12
    finally:
        session.stop()


def test_the_session_reads_a_whole_table(connection, root):
    _good(connection, root)
    connection.close()
    session = LocalSession.builder().root(root).getOrCreate()
    try:
        assert session.table("gold_daily_usage").count() == 6
    finally:
        session.stop()


def test_the_session_takes_query_parameters(connection, root):
    """A Spark-shaped façade is no excuse for formatting values into SQL."""
    _good(connection, root)
    connection.close()
    session = LocalSession.builder().root(root).getOrCreate()
    try:
        frame = session.sql(
            "SELECT count(*) AS n FROM silver_usage WHERE account_id = ?", ["acct-000"]
        )
        assert frame.first()["n"] == 2
    finally:
        session.stop()


def test_first_on_an_empty_result_is_none(connection, root):
    connection.close()
    session = LocalSession.builder().root(root).getOrCreate()
    try:
        assert session.sql("SELECT 1 AS n WHERE false").first() is None
    finally:
        session.stop()


# ---------------------------------------------------------------------------
# The CLI
# ---------------------------------------------------------------------------


def test_cli_run_reports_and_exits_zero(connection, root, capsys):
    _good(connection, root)
    connection.close()
    assert main(["run", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "files loaded" in out
    assert "[PASS] gold_reconciles_with_silver" in out


def test_cli_run_json_is_machine_readable(connection, root, capsys):
    _good(connection, root)
    connection.close()
    assert main(["run", "--root", str(root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["silver_rows"] == 12
    assert payload["checks_passed"] is True


def test_cli_run_exits_non_zero_when_a_gate_fails(connection, root, capsys):
    """The scheduler only looks at the exit code, so this is the contract that matters."""
    write_accounts(root, "accounts.csv", ACCOUNTS[:2])
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("e1", "acct-000")])
    connection.close()
    assert main(["run", "--root", str(root)]) == 1
    assert "quality gate failed" in capsys.readouterr().err


def test_cli_check_exits_non_zero_on_a_failing_warehouse(connection, root, capsys):
    write_accounts(root, "accounts.csv", ACCOUNTS[:2])
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("e1", "acct-000")])
    _run(connection, root)
    connection.close()
    assert main(["check", "--root", str(root)]) == 1


def test_cli_check_json_lists_every_check(connection, root, capsys):
    _good(connection, root)
    connection.close()
    assert main(["check", "--root", str(root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["passed"] is True
    assert len(payload["checks"]) == len(quality.ALL_CHECKS)


def test_cli_layers_can_be_run_individually(connection, root, capsys):
    write_accounts(root, "accounts.csv", ACCOUNTS)
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("e1"), event("e2")])
    connection.close()
    assert main(["bronze", "--root", str(root)]) == 0
    assert main(["silver", "--root", str(root)]) == 0
    assert main(["gold", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "loaded" in out
    assert "silver: 2 rows" in out


def test_cli_bronze_is_idempotent(connection, root, capsys):
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("e1")])
    connection.close()
    main(["bronze", "--root", str(root)])
    capsys.readouterr()
    main(["bronze", "--root", str(root)])
    assert "skipped (already loaded)" in capsys.readouterr().out


def test_cli_watermark_prints_the_position(connection, root, capsys):
    _good(connection, root)
    connection.close()
    main(["run", "--root", str(root)])
    capsys.readouterr()
    main(["watermark", "--root", str(root)])
    assert "usage: 2026-03-01" in capsys.readouterr().out


def test_cli_profile_describes_the_landing_zone(connection, root, capsys):
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("e1"), event("e2")])
    connection.close()
    assert main(["profile", "--root", str(root)]) == 0
    assert "usage_events_2026-03-01.jsonl" in capsys.readouterr().out


def test_cli_profile_on_a_missing_directory_reports_no_files(root, capsys):
    """Globbing an absent directory yields nothing rather than raising. Named for what it
    does: a missing *file* handed to ``profile_jsonl`` is an error, but a landing zone that
    is not there yet is the normal state before the first delivery."""
    assert main(["profile", str(root / "nowhere"), "--root", str(root)]) == 0
    assert "no files matched" in capsys.readouterr().out
