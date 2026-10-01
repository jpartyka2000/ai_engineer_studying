"""Silver: parse, normalise to UTC, keep money exact, reject loudly.

Every numeric expectation here is hand-computed and the arithmetic is in the docstring, so a
failure means the pipeline's meaning changed rather than that a snapshot drifted.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from etlduck import table_count
from etlduck.bronze import ingest_all
from etlduck.silver import (
    RowRejected,
    build_silver,
    parse_cents,
    parse_instant,
    parse_quantity,
)
from tests.conftest import event, write_raw_lines, write_usage


def _build(connection, root):
    """Ingest a landing zone and build silver from it."""
    ingest_all(connection, root)
    return build_silver(connection)


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------


def test_an_explicit_offset_is_converted_to_utc():
    """23:30 at -05:00 is 04:30 the next day in UTC. This single case is the whole reason
    the pipeline normalises before it buckets by date."""
    parsed = parse_instant("2026-03-01T23:30:00-05:00")
    assert parsed == datetime(2026, 3, 2, 4, 30, tzinfo=timezone.utc)
    assert parsed.date().isoformat() == "2026-03-02"


def test_a_positive_offset_is_converted_to_utc():
    """01:00 at +05:30 is 19:30 the previous day in UTC."""
    assert parse_instant("2026-03-02T01:00:00+05:30") == datetime(
        2026, 3, 1, 19, 30, tzinfo=timezone.utc
    )


def test_a_trailing_z_is_utc():
    assert parse_instant("2026-03-01T10:00:00Z") == datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)


def test_an_already_utc_timestamp_is_unchanged():
    assert parse_instant("2026-03-01T10:00:00+00:00") == datetime(
        2026, 3, 1, 10, 0, tzinfo=timezone.utc
    )


def test_a_naive_timestamp_is_rejected_rather_than_assumed_utc():
    """The decision this layer is built around. Assuming a zone moves an event across a day
    boundary for every customer in a negative offset, and nothing downstream can detect it."""
    with pytest.raises(RowRejected) as caught:
        parse_instant("2026-03-01 11:30:00")
    assert caught.value.reason == "naive_timestamp"


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_a_missing_timestamp_is_rejected(raw):
    with pytest.raises(RowRejected) as caught:
        parse_instant(raw)
    assert caught.value.reason == "missing_timestamp"


@pytest.mark.parametrize("raw", ["yesterday", "2026-13-45T00:00:00Z", "03/01/2026"])
def test_an_unparseable_timestamp_is_rejected(raw):
    with pytest.raises(RowRejected) as caught:
        parse_instant(raw)
    assert caught.value.reason == "unparseable_timestamp"


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------


def test_cents_parse_as_an_integer():
    assert parse_cents("1250") == 1250
    assert isinstance(parse_cents("1250"), int)


def test_a_decimal_amount_is_rejected_not_rounded():
    """The column is cents. A decimal in it means the producer sent dollars, which is worth
    an alert rather than a silent division by a hundred -- or worse, a rounding."""
    with pytest.raises(RowRejected) as caught:
        parse_cents("12.50")
    assert caught.value.reason == "amount_not_integer_cents"


def test_a_negative_amount_is_rejected():
    with pytest.raises(RowRejected) as caught:
        parse_cents("-100")
    assert caught.value.reason == "negative_amount"


def test_a_missing_amount_is_rejected():
    with pytest.raises(RowRejected) as caught:
        parse_cents(None)
    assert caught.value.reason == "missing_amount"


def test_quantities_parse_as_integers():
    assert parse_quantity("7") == 7


@pytest.mark.parametrize(
    ("raw", "reason"),
    [("1.5", "quantity_not_integer"), ("-1", "negative_quantity"), ("", "missing_quantity")],
)
def test_bad_quantities_are_rejected(raw, reason):
    with pytest.raises(RowRejected) as caught:
        parse_quantity(raw)
    assert caught.value.reason == reason


def test_money_sums_exactly(connection, root):
    """Three amounts that cannot be represented exactly as floats. 10 + 20 + 30 cents of a
    tenth each: in float arithmetic 0.1 + 0.2 + 0.3 is 0.6000000000000001, which is why this
    pipeline never leaves the integers."""
    write_usage(
        root,
        "usage_events_2026-03-01.jsonl",
        [
            event("e1", amount_cents="10"),
            event("e2", amount_cents="20"),
            event("e3", amount_cents="30"),
        ],
    )
    _build(connection, root)
    total = connection.execute("SELECT sum(amount_cents) FROM silver_usage").fetchone()[0]
    assert total == 60
    assert isinstance(total, int)


# ---------------------------------------------------------------------------
# Quarantine
# ---------------------------------------------------------------------------


def test_a_rejected_row_is_quarantined_with_its_reason(connection, root):
    write_usage(
        root,
        "usage_events_2026-03-01.jsonl",
        [event("ok"), event("bad", occurred_at="2026-03-01 11:30:00")],
    )
    result = _build(connection, root)

    assert result.rows_written == 1
    assert result.rows_quarantined == 1
    assert result.reasons == {"naive_timestamp": 1}
    row = connection.execute("SELECT event_id, reason FROM quarantine").fetchone()
    assert row == ("bad", "naive_timestamp")


def test_a_quarantined_row_is_not_in_silver(connection, root):
    """Counted and kept, never both dropped and uncounted."""
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("bad", amount_cents="12.50")])
    _build(connection, root)
    assert table_count(connection, "silver_usage") == 0
    assert table_count(connection, "quarantine") == 1


def test_an_unknown_event_type_is_quarantined(connection, root):
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("bad", event_type="beta_probe")])
    result = _build(connection, root)
    assert result.reasons == {"unknown_event_type": 1}


def test_an_event_with_no_account_is_quarantined(connection, root):
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("bad", account_id="")])
    result = _build(connection, root)
    assert result.reasons == {"missing_account_id": 1}


def test_an_unparseable_source_line_is_reported_as_such(connection, root):
    """Not as 'missing account'. A line bronze could not read is a different problem from a
    row with a field missing, and the reason column is what an on-call engineer reads first."""
    write_raw_lines(
        root, "usage_events_2026-03-01.jsonl", ['{"event_id": "e1", "account_id": "acct-0']
    )
    result = _build(connection, root)
    assert result.reasons == {"unparseable_source_line": 1}


def test_rebuilding_silver_replaces_rather_than_appends(connection, root):
    """Silver is a pure function of bronze, so building it twice must give the same table."""
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("e1"), event("e2")])
    _build(connection, root)
    first = table_count(connection, "silver_usage")
    build_silver(connection)
    assert table_count(connection, "silver_usage") == first == 2
    assert table_count(connection, "quarantine") == 0


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def test_a_replayed_event_collapses_to_one_row(connection, root):
    """At-least-once delivery means the same event_id arrives twice. Silver keeps one."""
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("e1", amount_cents="100")])
    write_usage(root, "usage_events_2026-03-02.jsonl", [event("e1", amount_cents="100")])
    result = _build(connection, root)

    assert table_count(connection, "bronze_usage") == 2
    assert result.rows_written == 1
    assert result.duplicates_collapsed == 1


def test_the_latest_delivery_wins(connection, root):
    """When a replay carries a corrected amount, the correction is what survives."""
    from etlduck.bronze import load_usage_file

    early = write_usage(root, "usage_events_2026-03-01.jsonl", [event("e1", amount_cents="100")])
    late = write_usage(root, "usage_events_2026-03-02.jsonl", [event("e1", amount_cents="900")])
    load_usage_file(connection, early, datetime(2026, 3, 1, tzinfo=timezone.utc))
    load_usage_file(connection, late, datetime(2026, 3, 2, tzinfo=timezone.utc))

    build_silver(connection)
    assert connection.execute("SELECT amount_cents FROM silver_usage").fetchone()[0] == 900


def test_deduplication_is_deterministic_across_rebuilds(connection, root):
    """Two files delivered in the same second, so ingested_at cannot break the tie. The
    tie-break on source_file then rowid is what makes repeated builds agree; without it this
    test fails intermittently, which is the worst way for it to fail."""
    from etlduck.bronze import load_usage_file

    same_instant = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
    first = write_usage(root, "usage_events_2026-03-01.jsonl", [event("e1", amount_cents="111")])
    second = write_usage(root, "usage_events_2026-03-02.jsonl", [event("e1", amount_cents="222")])
    load_usage_file(connection, first, same_instant)
    load_usage_file(connection, second, same_instant)

    chosen = set()
    for _ in range(5):
        build_silver(connection)
        chosen.add(connection.execute("SELECT amount_cents FROM silver_usage").fetchone()[0])
    assert len(chosen) == 1


# ---------------------------------------------------------------------------
# Against the committed landing zone
# ---------------------------------------------------------------------------


def test_the_committed_data_yields_the_expected_silver(seeded):
    """400 kept, 10 quarantined, 1 duplicate collapsed, from 411 bronze rows.

    411 = 2 days x (200 good + 5 deliberate defects) + 1 replay. The replay collapses, so 410
    distinct events; 10 of those break a rule.
    """
    _, result = seeded
    assert result.silver.rows_written == 400
    assert result.silver.rows_quarantined == 10
    assert result.silver.duplicates_collapsed == 1
    assert result.silver.rows_considered == 410


def test_every_quarantine_reason_is_exercised_by_the_committed_data(seeded):
    """Two of each, one per generated day. A suite whose fixtures only contain clean rows
    cannot tell a working quarantine from a silently-dropping one."""
    _, result = seeded
    assert result.silver.reasons == {
        "amount_not_integer_cents": 2,
        "missing_account_id": 2,
        "naive_timestamp": 2,
        "unknown_event_type": 2,
        "unparseable_source_line": 2,
    }


def test_the_committed_quarantine_rate_is_inside_the_budget(seeded):
    """2.44%, against a 5% budget. Deliberately not close to the limit: an exercise that
    adds one more rejection should not trip an unrelated quality gate."""
    _, result = seeded
    assert result.silver.quarantine_fraction < 0.03


def test_normalising_moves_a_real_share_of_events_across_a_day_boundary(seeded):
    """58 of 400 events land on a different UTC date than their raw timestamp's local date.

    That is the measured size of the problem: large enough that bucketing in the wrong zone
    misstates a day's revenue, small enough that it reads as noise if nobody checks. Asserted
    as a band rather than exactly 58 so a change to the generator's volume does not fail this
    for the wrong reason.
    """
    connection, _ = seeded
    shifted = connection.execute(
        "SELECT count(*) FROM silver_usage s JOIN bronze_usage b USING (event_id) "
        "WHERE CAST(substr(b.occurred_at_raw, 1, 10) AS DATE) <> s.event_date"
    ).fetchone()[0]
    assert 20 < shifted < 120


def test_event_date_is_always_the_utc_date_of_the_instant(seeded):
    connection, _ = seeded
    mismatched = connection.execute(
        "SELECT count(*) FROM silver_usage WHERE event_date <> CAST(occurred_at AS DATE)"
    ).fetchone()[0]
    assert mismatched == 0
