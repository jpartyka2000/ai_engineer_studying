"""The end-to-end run: bronze, silver, gold, quality, watermark.

Ordering here is the contract, and two parts of it are load-bearing:

**Quality gates run before the watermark moves.** The watermark is the record of what has
been successfully processed, so it may only advance over data that passed its checks. Moving
it first and validating afterwards means a bad batch is marked done and never revisited.

**The watermark is derived from event time, not wall-clock time.** ``max_event_time`` reads
the newest instant actually present in silver. Usage telemetry arrives late as a matter of
course; a watermark set to "now" skips everything still in flight.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from etlduck import quality
from etlduck.bronze import LoadResult, ingest_all
from etlduck.gold import GoldResult, build_gold
from etlduck.silver import SilverResult, build_silver
from etlduck.watermark import max_event_time, watermark_advanced_on_success

#: The stream name the usage watermark is stored under.
USAGE_STREAM = "usage"


@dataclass
class RunResult:
    """Everything one pipeline run did."""

    loads: list[LoadResult] = field(default_factory=list)
    silver: SilverResult | None = None
    gold: GoldResult | None = None
    checks: list[quality.Check] = field(default_factory=list)

    @property
    def files_loaded(self) -> int:
        """How many files actually contributed rows this run."""
        return sum(1 for load in self.loads if load.loaded)

    @property
    def files_skipped(self) -> int:
        """How many files were recognised as already loaded."""
        return sum(1 for load in self.loads if load.skipped_as_duplicate)

    @property
    def ok(self) -> bool:
        """Whether every quality check passed."""
        return all(check.passed for check in self.checks)

    def summary(self) -> str:
        """Render a run as a short report."""
        lines = [
            f"files loaded      : {self.files_loaded} ({self.files_skipped} already loaded)",
        ]
        if self.silver is not None:
            lines += [
                f"silver rows       : {self.silver.rows_written}",
                f"quarantined       : {self.silver.rows_quarantined} "
                f"({self.silver.quarantine_fraction:.2%})",
                f"duplicates        : {self.silver.duplicates_collapsed} collapsed",
            ]
            if self.silver.reasons:
                for reason, count in sorted(self.silver.reasons.items()):
                    lines.append(f"  - {reason}: {count}")
        if self.gold is not None:
            lines += [
                f"gold rows         : {self.gold.rows_written} "
                f"over {self.gold.distinct_dates} dates",
                f"total amount      : {self.gold.total_amount_cents} cents",
            ]
        lines.append("checks:")
        lines += [f"  {check}" for check in self.checks]
        return "\n".join(lines)


def run_pipeline(
    connection: duckdb.DuckDBPyConnection,
    root: str | Path | None = None,
    strict: bool = True,
) -> RunResult:
    """Run every layer in order and advance the watermark on success.

    Args:
        connection: An open warehouse connection.
        root: Project root override, for tests.
        strict: Raise :class:`~etlduck.quality.QualityFailure` when a check fails. Set
            ``False`` only to inspect a broken warehouse; the watermark still does not
            move, because the point of the gate is what it protects, not whether it shouts.

    Returns:
        A :class:`RunResult`.

    Raises:
        QualityFailure: When ``strict`` and any check failed.
    """
    result = RunResult()
    result.loads = ingest_all(connection, root)
    result.silver = build_silver(connection)
    result.gold = build_gold(connection)
    result.checks = quality.run_all(connection)

    if not result.ok:
        if strict:
            quality.assert_ok(result.checks)
        return result

    with watermark_advanced_on_success(connection, USAGE_STREAM, max_event_time(connection)):
        pass
    return result
