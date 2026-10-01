"""Silver to gold: the daily per-account rollup the business reads.

Two things are easy to get wrong in this layer and both inflate revenue rather than losing
it, which is the direction nobody notices until an auditor does.

**The account dimension must be collapsed before it is joined.** ``bronze_accounts`` holds
one row per delivery, so an account that appears in two exports appears twice. Joining
usage to that doubles every event for that account. The join here is against a
deduplicated view, never the raw table.

**The date bucket comes from silver's UTC instant.** ``silver_usage.event_date`` is derived
from the normalised UTC timestamp, so re-deriving a date here -- from anything else, in any
other zone -- would move events between days for exactly the accounts in offsets far from
UTC.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

#: One row per account, latest delivery wins. ``source_file`` then ``rowid`` break ties so
#: the choice is total and two runs agree.
LATEST_ACCOUNTS_SQL = """
SELECT account_id, name, plan, country
FROM (
    SELECT *, row_number() OVER (
        PARTITION BY account_id
        ORDER BY ingested_at DESC, source_file ASC, rowid ASC
    ) AS rn
    FROM bronze_accounts
)
WHERE rn = 1
"""

#: The rollup. A LEFT JOIN so usage for an account missing from the dimension is still
#: counted -- losing revenue because a dimension export was late is worse than reporting
#: it with an unknown plan. ``plan`` is then NULL, which the quality checks look for.
ROLLUP_SQL = f"""
INSERT INTO gold_daily_usage (event_date, account_id, plan, events, quantity, amount_cents)
SELECT
    u.event_date,
    u.account_id,
    a.plan,
    count(*)            AS events,
    sum(u.quantity)     AS quantity,
    sum(u.amount_cents) AS amount_cents
FROM silver_usage AS u
LEFT JOIN ({LATEST_ACCOUNTS_SQL}) AS a USING (account_id)
GROUP BY u.event_date, u.account_id, a.plan
ORDER BY u.event_date, u.account_id
"""


@dataclass(frozen=True)
class GoldResult:
    """What one gold build produced."""

    rows_written: int
    distinct_dates: int
    total_amount_cents: int


def build_gold(connection: duckdb.DuckDBPyConnection) -> GoldResult:
    """Rebuild ``gold_daily_usage`` from ``silver_usage``.

    A full rebuild inside one transaction, for the same reason silver rebuilds: gold is a
    pure function of silver, so recomputing it is idempotent by construction and needs no
    merge logic to get wrong.

    Args:
        connection: An open warehouse connection.

    Returns:
        A :class:`GoldResult`.
    """
    connection.execute("BEGIN TRANSACTION")
    try:
        connection.execute("DELETE FROM gold_daily_usage")
        connection.execute(ROLLUP_SQL)
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise

    row = connection.execute(
        "SELECT count(*), count(DISTINCT event_date), coalesce(sum(amount_cents), 0) "
        "FROM gold_daily_usage"
    ).fetchone()
    return GoldResult(
        rows_written=int(row[0]), distinct_dates=int(row[1]), total_amount_cents=int(row[2])
    )


def daily_totals(connection: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Return ``(event_date, events, amount_cents)`` per day, ascending.

    Used by the validation notebook and by tests that assert a day's total rather than a
    single account's.
    """
    return connection.execute(
        "SELECT event_date, sum(events), sum(amount_cents) FROM gold_daily_usage "
        "GROUP BY event_date ORDER BY event_date"
    ).fetchall()
