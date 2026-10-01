"""Bronze: load exactly once, and keep everything that arrived.

Idempotency is the property this layer exists to guarantee. The tests below are the ones
that would fail if a retry duplicated rows, which is the single most common way an ETL
pipeline overstates a total.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from etlduck import table_count
from etlduck.bronze import (
    UNPARSEABLE_MARKER,
    already_loaded,
    content_hash,
    ingest_all,
    load_usage_file,
    read_usage_jsonl,
)
from tests.conftest import event, write_accounts, write_raw_lines, write_usage

STAMP = datetime(2026, 3, 5, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Content hashing
# ---------------------------------------------------------------------------


def test_identical_content_hashes_the_same(root):
    """Two files with the same bytes are the same delivery, whatever they are called."""
    first = write_usage(root, "usage_events_a.jsonl", [event("e1")])
    second = write_usage(root, "usage_events_b.jsonl", [event("e1")])
    assert content_hash(first) == content_hash(second)


def test_changed_content_hashes_differently(root):
    """One changed field must produce a different hash, or a re-export is missed."""
    path = write_usage(root, "usage_events_a.jsonl", [event("e1", amount_cents="100")])
    before = content_hash(path)
    write_usage(root, "usage_events_a.jsonl", [event("e1", amount_cents="101")])
    assert content_hash(path) != before


# ---------------------------------------------------------------------------
# Loading once
# ---------------------------------------------------------------------------


def test_a_file_loads_its_rows(connection, root):
    path = write_usage(root, "usage_events_a.jsonl", [event("e1"), event("e2")])
    result = load_usage_file(connection, path, STAMP)
    assert result.rows_inserted == 2
    assert result.loaded
    assert table_count(connection, "bronze_usage") == 2


def test_loading_the_same_file_twice_inserts_nothing_the_second_time(connection, root):
    """The property. A retried job must not double the warehouse."""
    path = write_usage(root, "usage_events_a.jsonl", [event("e1"), event("e2")])
    load_usage_file(connection, path, STAMP)
    second = load_usage_file(connection, path, STAMP)

    assert second.skipped_as_duplicate
    assert second.rows_inserted == 0
    assert table_count(connection, "bronze_usage") == 2


def test_loading_ten_times_is_the_same_as_loading_once(connection, root):
    """Stated separately from the twice case because an off-by-one in the load log would
    pass that one and fail this."""
    path = write_usage(root, "usage_events_a.jsonl", [event("e1"), event("e2"), event("e3")])
    for _ in range(10):
        load_usage_file(connection, path, STAMP)
    assert table_count(connection, "bronze_usage") == 3
    assert table_count(connection, "load_log") == 1


def test_a_file_re_exported_with_new_content_is_loaded_again(connection, root):
    """The other half of the contract. Skipping on the *name* alone would silently drop a
    corrected export, which is a worse failure than duplicating one."""
    path = write_usage(root, "usage_events_a.jsonl", [event("e1")])
    load_usage_file(connection, path, STAMP)

    write_usage(root, "usage_events_a.jsonl", [event("e1"), event("e2")])
    second = load_usage_file(connection, path, STAMP)

    assert second.loaded
    assert table_count(connection, "bronze_usage") == 3
    assert table_count(connection, "load_log") == 2


def test_the_load_log_records_the_row_count(connection, root):
    path = write_usage(root, "usage_events_a.jsonl", [event("e1"), event("e2")])
    load_usage_file(connection, path, STAMP)
    assert connection.execute("SELECT row_count FROM load_log").fetchone()[0] == 2


def test_already_loaded_is_keyed_on_name_and_hash(connection, root):
    path = write_usage(root, "usage_events_a.jsonl", [event("e1")])
    digest = content_hash(path)
    assert not already_loaded(connection, path.name, digest)
    load_usage_file(connection, path, STAMP)
    assert already_loaded(connection, path.name, digest)
    assert not already_loaded(connection, path.name, "a" * 64)
    assert not already_loaded(connection, "other.jsonl", digest)


def test_an_empty_file_is_recorded_as_loaded(connection, root):
    """An empty delivery is a real delivery. Recording it stops the pipeline re-reading it
    forever, and `loaded` rather than the row count is how a caller tells the difference."""
    path = write_raw_lines(root, "usage_events_a.jsonl", [])
    result = load_usage_file(connection, path, STAMP)
    assert result.loaded
    assert result.rows_inserted == 0
    assert table_count(connection, "load_log") == 1
    assert load_usage_file(connection, path, STAMP).skipped_as_duplicate


# ---------------------------------------------------------------------------
# Keeping what arrived
# ---------------------------------------------------------------------------


def test_an_unparseable_line_is_kept_not_dropped(root):
    """Bronze is the only place that still knows a malformed line existed."""
    path = write_raw_lines(
        root,
        "usage_events_a.jsonl",
        ['{"event_id": "e1", "account_id": "acct-000", "event_type": "api_c'],
    )
    rows = read_usage_jsonl(path)
    assert len(rows) == 1
    assert rows[0]["event_type"] == UNPARSEABLE_MARKER
    assert rows[0]["event_id"] == f"{path.name}:1"


def test_blank_lines_are_not_rows(root):
    path = write_raw_lines(root, "usage_events_a.jsonl", ["", "   ", ""])
    assert read_usage_jsonl(path) == []


def test_every_value_lands_as_text(connection, root):
    """Bronze coerces nothing. A quantity sent as a JSON number is stored as its text, so
    the decision about what it means belongs to silver and is visible there."""
    path = write_raw_lines(
        root,
        "usage_events_a.jsonl",
        [
            '{"event_id": "e1", "account_id": "acct-000", "event_type": "api_call", '
            '"occurred_at": "2026-03-01T10:00:00+00:00", "quantity": 7, "amount_cents": 250}'
        ],
    )
    load_usage_file(connection, path, STAMP)
    row = connection.execute("SELECT quantity_raw, amount_cents_raw FROM bronze_usage").fetchone()
    assert row == ("7", "250")


def test_the_source_file_is_recorded_on_every_row(connection, root):
    path = write_usage(root, "usage_events_a.jsonl", [event("e1"), event("e2")])
    load_usage_file(connection, path, STAMP)
    names = connection.execute("SELECT DISTINCT source_file FROM bronze_usage").fetchall()
    assert names == [("usage_events_a.jsonl",)]


# ---------------------------------------------------------------------------
# Ingesting a whole landing zone
# ---------------------------------------------------------------------------


def test_ingest_all_loads_accounts_before_usage(connection, root):
    """Order matters for a reader of the log, and sorted order makes a partial failure
    leave a predictable prefix rather than an arbitrary subset."""
    write_accounts(
        root,
        "accounts.csv",
        [{"account_id": "acct-000", "name": "A", "plan": "team", "country": "DE"}],
    )
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("e1")])
    results = ingest_all(connection, root)
    assert [r.source_file for r in results] == ["accounts.csv", "usage_events_2026-03-01.jsonl"]


def test_ingest_all_is_idempotent(connection, root):
    write_accounts(
        root,
        "accounts.csv",
        [{"account_id": "acct-000", "name": "A", "plan": "team", "country": "DE"}],
    )
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("e1"), event("e2")])

    ingest_all(connection, root)
    second = ingest_all(connection, root)

    assert all(result.skipped_as_duplicate for result in second)
    assert table_count(connection, "bronze_usage") == 2
    assert table_count(connection, "bronze_accounts") == 1


def test_ingest_all_ignores_files_it_does_not_recognise(connection, root):
    """A landing zone collects junk -- editor backups, checksums, a README. Only the two
    declared patterns are loaded."""
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("e1")])
    (root / "raw" / "notes.txt").write_text("ignore me\n", encoding="utf-8")
    (root / "raw" / "usage_events_2026-03-01.jsonl.bak").write_text("{}\n", encoding="utf-8")
    results = ingest_all(connection, root)
    assert [r.source_file for r in results] == ["usage_events_2026-03-01.jsonl"]


# ---------------------------------------------------------------------------
# Against the committed landing zone
# ---------------------------------------------------------------------------


def test_the_committed_landing_zone_loads_the_expected_rows(seeded):
    """411 usage rows: 200 well-formed events per day, five deliberate defects per day, and
    one replayed event on the second day. Exact because the generator is seeded."""
    connection, _ = seeded
    assert table_count(connection, "bronze_usage") == 411
    assert table_count(connection, "bronze_accounts") == 10
    assert table_count(connection, "load_log") == 4


def test_rerunning_the_committed_pipeline_changes_nothing(seeded, seeded_root):
    """The integration-level statement of idempotency."""
    connection, first = seeded
    from etlduck import run_pipeline

    before = table_count(connection, "bronze_usage")
    second = run_pipeline(connection, seeded_root)

    assert second.files_loaded == 0
    assert second.files_skipped == 4
    assert table_count(connection, "bronze_usage") == before
    assert second.gold.total_amount_cents == first.gold.total_amount_cents


@pytest.mark.parametrize("name", ["accounts.csv", "accounts_delta.csv"])
def test_both_account_deliveries_are_loaded(seeded, name):
    """The dimension arrives in two files and both land in bronze. Collapsing them is
    gold's job, not the loader's."""
    connection, _ = seeded
    count = connection.execute(
        "SELECT count(*) FROM bronze_accounts WHERE source_file = ?", [name]
    ).fetchone()[0]
    assert count > 0
