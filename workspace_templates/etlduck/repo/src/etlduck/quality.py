"""Data-quality gates.

Each check returns a :class:`Check` rather than raising, so one run reports everything that
is wrong instead of stopping at the first thing. The job decides what to do with the
collection; ``run_all`` plus ``assert_ok`` is the usual pairing.

The most important one is the reconciliation: gold's money must equal silver's money to the
cent. Every other check here could pass while the rollup quietly double-counted a join, and
that is the failure mode this layer exists for.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from etlduck.config import MAX_QUARANTINE_FRACTION, MIN_ACCOUNTS_EXPECTED


@dataclass(frozen=True)
class Check:
    """One quality finding."""

    name: str
    passed: bool
    detail: str = ""

    def __str__(self) -> str:
        """Render as a single reportable line."""
        mark = "PASS" if self.passed else "FAIL"
        return f"[{mark}] {self.name}{': ' + self.detail if self.detail else ''}"


class QualityFailure(RuntimeError):
    """Raised by :func:`assert_ok` when any check failed."""


def check_gold_reconciles_with_silver(connection: duckdb.DuckDBPyConnection) -> Check:
    """Gold's totals must equal silver's, exactly.

    Compared as integers, so there is no tolerance and none is needed. A mismatch means the
    rollup lost or duplicated rows -- most often a dimension join against an undeduplicated
    table, which multiplies rather than adding.
    """
    silver = connection.execute(
        "SELECT count(*), coalesce(sum(quantity), 0), coalesce(sum(amount_cents), 0) "
        "FROM silver_usage"
    ).fetchone()
    gold = connection.execute(
        "SELECT coalesce(sum(events), 0), coalesce(sum(quantity), 0), "
        "coalesce(sum(amount_cents), 0) FROM gold_daily_usage"
    ).fetchone()
    if tuple(int(v) for v in silver) == tuple(int(v) for v in gold):
        return Check("gold_reconciles_with_silver", True, f"{int(gold[2])} cents")
    return Check(
        "gold_reconciles_with_silver",
        False,
        f"silver={tuple(int(v) for v in silver)} gold={tuple(int(v) for v in gold)}",
    )


def check_quarantine_within_budget(connection: duckdb.DuckDBPyConnection) -> Check:
    """The share of rejected rows must stay under the configured budget.

    A rising quarantine rate is the earliest signal that an upstream producer changed its
    format. The budget is deliberately not zero: a handful of malformed rows is normal and
    blocking the pipeline on them would mean no warehouse at all on a bad day.
    """
    kept = int(connection.execute("SELECT count(*) FROM silver_usage").fetchone()[0])
    rejected = int(connection.execute("SELECT count(*) FROM quarantine").fetchone()[0])
    considered = kept + rejected
    fraction = rejected / considered if considered else 0.0
    if fraction <= MAX_QUARANTINE_FRACTION:
        return Check("quarantine_within_budget", True, f"{fraction:.2%} of {considered}")
    return Check(
        "quarantine_within_budget",
        False,
        f"{fraction:.2%} of {considered} rows rejected, budget is {MAX_QUARANTINE_FRACTION:.0%}",
    )


def check_accounts_present(connection: duckdb.DuckDBPyConnection) -> Check:
    """The dimension must not be empty or implausibly small.

    Catches the case where the accounts export arrived truncated: usage still loads, gold
    still builds, and every row comes out with a NULL plan.
    """
    distinct = int(
        connection.execute("SELECT count(DISTINCT account_id) FROM bronze_accounts").fetchone()[0]
    )
    if distinct >= MIN_ACCOUNTS_EXPECTED:
        return Check("accounts_present", True, f"{distinct} accounts")
    return Check(
        "accounts_present",
        False,
        f"only {distinct} distinct accounts, expected at least {MIN_ACCOUNTS_EXPECTED}",
    )


def check_no_unattributed_usage(connection: duckdb.DuckDBPyConnection) -> Check:
    """Every rolled-up account should resolve to a plan.

    A warning-shaped check: usage with no matching dimension row is counted rather than
    dropped by design, so this failing means the dimension is incomplete, not that the
    rollup is wrong.
    """
    unattributed = int(
        connection.execute("SELECT count(*) FROM gold_daily_usage WHERE plan IS NULL").fetchone()[0]
    )
    if unattributed == 0:
        return Check("no_unattributed_usage", True)
    return Check(
        "no_unattributed_usage",
        False,
        f"{unattributed} gold rows have no plan, so their account is missing from the dimension",
    )


def check_one_row_per_account_day(connection: duckdb.DuckDBPyConnection) -> Check:
    """Gold's grain must be exactly one row per (date, account).

    The primary key enforces this at write time, so a failure here means somebody widened
    the grain without widening the key -- at which point every consumer summing the table
    double counts.
    """
    duplicates = int(
        connection.execute(
            "SELECT count(*) FROM (SELECT event_date, account_id FROM gold_daily_usage "
            "GROUP BY event_date, account_id HAVING count(*) > 1)"
        ).fetchone()[0]
    )
    if duplicates == 0:
        return Check("one_row_per_account_day", True)
    return Check("one_row_per_account_day", False, f"{duplicates} (date, account) pairs repeat")


def check_dates_are_utc_consistent(connection: duckdb.DuckDBPyConnection) -> Check:
    """``event_date`` must be the UTC date of ``occurred_at``.

    Re-derived here from the instant rather than trusted, because a date computed in a
    local zone differs for only a slice of rows -- those within a few hours of midnight --
    which is small enough to look like noise and large enough to misstate a day's revenue.
    """
    mismatched = int(
        connection.execute(
            "SELECT count(*) FROM silver_usage WHERE event_date <> CAST(occurred_at AS DATE)"
        ).fetchone()[0]
    )
    if mismatched == 0:
        return Check("dates_are_utc_consistent", True)
    return Check(
        "dates_are_utc_consistent",
        False,
        f"{mismatched} silver rows have an event_date that is not the UTC date of their timestamp",
    )


#: Run in this order: reconciliation first, because if gold and silver disagree the rest of
#: the report is about a table nobody should be reading yet.
ALL_CHECKS = (
    check_gold_reconciles_with_silver,
    check_one_row_per_account_day,
    check_dates_are_utc_consistent,
    check_quarantine_within_budget,
    check_accounts_present,
    check_no_unattributed_usage,
)


def run_all(connection: duckdb.DuckDBPyConnection) -> list[Check]:
    """Run every check and return the findings in order."""
    return [check(connection) for check in ALL_CHECKS]


def assert_ok(checks: list[Check]) -> None:
    """Raise if any check failed.

    Args:
        checks: The findings from :func:`run_all`.

    Raises:
        QualityFailure: Listing every failure, not just the first, so one run tells the
            on-call engineer everything.
    """
    failures = [check for check in checks if not check.passed]
    if failures:
        raise QualityFailure("; ".join(str(check) for check in failures))
