"""Gold: roll up without multiplying.

The failure this layer invites is a fan-out join, and it inflates revenue rather than losing
it. ``test_a_redelivered_account_does_not_double_its_usage`` is the one that matters; the rest
pin the grain and the reconciliation that would catch it a second way.
"""

from __future__ import annotations

from etlduck import table_count
from etlduck.bronze import ingest_all, load_accounts_file
from etlduck.gold import build_gold, daily_totals
from etlduck.quality import check_gold_reconciles_with_silver
from etlduck.silver import build_silver
from tests.conftest import event, write_accounts, write_usage

ACCOUNTS = [
    {"account_id": "acct-000", "name": "Alpha", "plan": "team", "country": "DE"},
    {"account_id": "acct-001", "name": "Beta", "plan": "free", "country": "US"},
]


def _run(connection, root):
    """Ingest, build silver, build gold."""
    ingest_all(connection, root)
    build_silver(connection)
    return build_gold(connection)


# ---------------------------------------------------------------------------
# The grain
# ---------------------------------------------------------------------------


def test_one_row_per_account_and_date(connection, root):
    """Two accounts, two dates, four events: four gold rows."""
    write_accounts(root, "accounts.csv", ACCOUNTS)
    write_usage(
        root,
        "usage_events_2026-03-01.jsonl",
        [
            event("e1", "acct-000", occurred_at="2026-03-01T10:00:00+00:00"),
            event("e2", "acct-001", occurred_at="2026-03-01T11:00:00+00:00"),
            event("e3", "acct-000", occurred_at="2026-03-02T10:00:00+00:00"),
            event("e4", "acct-001", occurred_at="2026-03-02T11:00:00+00:00"),
        ],
    )
    result = _run(connection, root)
    assert result.rows_written == 4
    assert result.distinct_dates == 2


def test_events_on_the_same_day_are_summed(connection, root):
    """Three events for one account on one day: quantity 1+2+3, amount 100+200+300."""
    write_accounts(root, "accounts.csv", ACCOUNTS)
    write_usage(
        root,
        "usage_events_2026-03-01.jsonl",
        [
            event("e1", "acct-000", quantity="1", amount_cents="100"),
            event("e2", "acct-000", quantity="2", amount_cents="200"),
            event("e3", "acct-000", quantity="3", amount_cents="300"),
        ],
    )
    _run(connection, root)
    row = connection.execute(
        "SELECT events, quantity, amount_cents FROM gold_daily_usage"
    ).fetchone()
    assert row == (3, 6, 600)


def test_the_plan_comes_from_the_dimension(connection, root):
    write_accounts(root, "accounts.csv", ACCOUNTS)
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("e1", "acct-001")])
    _run(connection, root)
    assert connection.execute("SELECT plan FROM gold_daily_usage").fetchone()[0] == "free"


# ---------------------------------------------------------------------------
# The fan-out
# ---------------------------------------------------------------------------


def test_a_redelivered_account_does_not_double_its_usage(connection, root):
    """The decisive test. ``acct-000`` arrives in two deliveries, so bronze_accounts holds
    two rows for it. One event of 500 cents must stay 500 cents, not 1000.

    A join against the raw dimension table multiplies every usage row by the number of
    deliveries for its account, which looks like growth and is the hardest kind of error to
    notice because nothing fails.
    """
    write_accounts(root, "accounts.csv", ACCOUNTS)
    write_accounts(
        root,
        "accounts_delta.csv",
        [{"account_id": "acct-000", "name": "Alpha", "plan": "enterprise", "country": "DE"}],
    )
    write_usage(
        root, "usage_events_2026-03-01.jsonl", [event("e1", "acct-000", amount_cents="500")]
    )

    _run(connection, root)

    assert table_count(connection, "bronze_accounts") == 3
    rows = connection.execute(
        "SELECT account_id, events, amount_cents FROM gold_daily_usage"
    ).fetchall()
    assert rows == [("acct-000", 1, 500)]


def test_the_latest_delivery_supplies_the_plan(connection, root):
    """``acct-000`` was upgraded in the second delivery, so gold must say enterprise."""
    from datetime import datetime, timezone

    first = write_accounts(root, "accounts.csv", ACCOUNTS)
    second = write_accounts(
        root,
        "accounts_delta.csv",
        [{"account_id": "acct-000", "name": "Alpha", "plan": "enterprise", "country": "DE"}],
    )
    load_accounts_file(connection, first, datetime(2026, 3, 1, tzinfo=timezone.utc))
    load_accounts_file(connection, second, datetime(2026, 3, 2, tzinfo=timezone.utc))
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("e1", "acct-000")])

    _run(connection, root)
    assert connection.execute("SELECT plan FROM gold_daily_usage").fetchone()[0] == "enterprise"


def test_usage_for_an_unknown_account_is_still_counted(connection, root):
    """A late dimension export must not cost us the revenue. The plan is NULL and a quality
    check reports it, which is a better outcome than a row that silently vanishes."""
    write_accounts(root, "accounts.csv", ACCOUNTS)
    write_usage(
        root, "usage_events_2026-03-01.jsonl", [event("e1", "acct-999", amount_cents="700")]
    )
    _run(connection, root)
    row = connection.execute(
        "SELECT account_id, plan, amount_cents FROM gold_daily_usage"
    ).fetchone()
    assert row == ("acct-999", None, 700)


# ---------------------------------------------------------------------------
# Rebuild and reconciliation
# ---------------------------------------------------------------------------


def test_rebuilding_gold_is_idempotent(connection, root):
    write_accounts(root, "accounts.csv", ACCOUNTS)
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("e1"), event("e2")])
    first = _run(connection, root)
    second = build_gold(connection)
    assert (second.rows_written, second.total_amount_cents) == (
        first.rows_written,
        first.total_amount_cents,
    )


def test_gold_reconciles_with_silver(connection, root):
    write_accounts(root, "accounts.csv", ACCOUNTS)
    write_usage(
        root,
        "usage_events_2026-03-01.jsonl",
        [event("e1", "acct-000", amount_cents="123"), event("e2", "acct-001", amount_cents="456")],
    )
    _run(connection, root)
    assert check_gold_reconciles_with_silver(connection).passed


def test_the_reconciliation_check_notices_a_double_count(connection, root):
    """Proves the gate works rather than merely passing. Gold is doubled by hand here, and the
    check must say so -- a reconciliation that cannot fail is not a reconciliation."""
    write_accounts(root, "accounts.csv", ACCOUNTS)
    write_usage(
        root, "usage_events_2026-03-01.jsonl", [event("e1", "acct-000", amount_cents="500")]
    )
    _run(connection, root)
    connection.execute("UPDATE gold_daily_usage SET amount_cents = amount_cents * 2")
    check = check_gold_reconciles_with_silver(connection)
    assert not check.passed
    assert "silver=" in check.detail


def test_daily_totals_are_ordered_by_date(connection, root):
    write_accounts(root, "accounts.csv", ACCOUNTS)
    write_usage(
        root,
        "usage_events_2026-03-01.jsonl",
        [
            event("e1", occurred_at="2026-03-03T10:00:00+00:00"),
            event("e2", occurred_at="2026-03-01T10:00:00+00:00"),
            event("e3", occurred_at="2026-03-02T10:00:00+00:00"),
        ],
    )
    _run(connection, root)
    dates = [row[0].isoformat() for row in daily_totals(connection)]
    assert dates == ["2026-03-01", "2026-03-02", "2026-03-03"]


# ---------------------------------------------------------------------------
# Against the committed landing zone
# ---------------------------------------------------------------------------


def test_the_committed_data_yields_the_expected_gold(seeded):
    """30 rows over 4 UTC dates totalling 817691 cents.

    Four dates from two days of input is correct, not a bug: events near midnight in offsets
    either side of UTC legitimately fall into the adjacent UTC day.
    """
    _, result = seeded
    assert result.gold.rows_written == 30
    assert result.gold.distinct_dates == 4
    assert result.gold.total_amount_cents == 817691


def test_the_committed_gold_reconciles(seeded):
    """The dimension really does arrive twice in the committed data, so this is the fan-out
    guard operating on the realistic case rather than a two-row fixture."""
    connection, _ = seeded
    assert table_count(connection, "bronze_accounts") == 10
    assert check_gold_reconciles_with_silver(connection).passed


def test_the_committed_gold_has_no_repeated_account_day(seeded):
    connection, _ = seeded
    repeated = connection.execute(
        "SELECT count(*) FROM (SELECT event_date, account_id FROM gold_daily_usage "
        "GROUP BY event_date, account_id HAVING count(*) > 1)"
    ).fetchone()[0]
    assert repeated == 0
