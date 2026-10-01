"""etlduck -- a medallion warehouse on DuckDB.

Raw exports land in ``raw/``, are copied verbatim into **bronze**, parsed and normalised into
**silver**, and rolled up into **gold**. One process, one file, no cluster: see
``spark_compat`` for why the jobs and notebooks are nevertheless shaped like Databricks
assets.

A run, end to end:

    >>> import tempfile
    >>> from pathlib import Path
    >>> from etlduck import connect, run_pipeline
    >>> root = Path(tempfile.mkdtemp())
    >>> (root / "raw").mkdir()
    >>> _ = (root / "raw" / "accounts.csv").write_text(
    ...     "account_id,name,plan,country\\n"
    ...     + "".join(f"acct-{n},Name {n},team,DE\\n" for n in range(5))
    ... )
    >>> _ = (root / "raw" / "usage_events_2026-03-01.jsonl").write_text(
    ...     '{"event_id": "e1", "account_id": "acct-0", "event_type": "api_call",'
    ...     ' "occurred_at": "2026-03-01T10:00:00+00:00", "quantity": "2",'
    ...     ' "amount_cents": "150"}\\n'
    ... )
    >>> with connect(root) as _unused:  # doctest: +SKIP
    ...     pass
    >>> connection = connect(root)
    >>> result = run_pipeline(connection, root)
    >>> result.silver.rows_written
    1
    >>> result.gold.total_amount_cents
    150
    >>> result.ok
    True
    >>> connection.close()

The four properties this package is built around, each pinned by tests:

* **Idempotency.** Re-running a load does not duplicate rows; re-running silver or gold
  recomputes them from scratch.
* **Monotonic watermarks.** A watermark never moves backwards and never advances over work
  that failed its quality gates.
* **Determinism.** Every tie-break -- deduplication, dimension selection -- is explicit, so
  two runs over the same input agree.
* **Loud rejection.** A row that cannot be parsed is quarantined with a reason and counted,
  never dropped.
"""

from etlduck.bronze import LoadResult, ingest_all, load_accounts_file, load_usage_file
from etlduck.config import Paths, paths
from etlduck.db import connect, table_count, warehouse
from etlduck.gold import GoldResult, build_gold, daily_totals
from etlduck.pipeline import RunResult, run_pipeline
from etlduck.profile import FileProfile, profile_jsonl, profile_landing_zone
from etlduck.quality import Check, QualityFailure, assert_ok, run_all
from etlduck.silver import SilverResult, build_silver, parse_cents, parse_instant
from etlduck.watermark import (
    WatermarkRegression,
    advance_watermark,
    get_watermark,
    max_event_time,
)

__version__ = "0.3.0"

__all__ = [
    "Check",
    "FileProfile",
    "GoldResult",
    "LoadResult",
    "Paths",
    "QualityFailure",
    "RunResult",
    "SilverResult",
    "WatermarkRegression",
    "advance_watermark",
    "assert_ok",
    "build_gold",
    "build_silver",
    "connect",
    "daily_totals",
    "get_watermark",
    "ingest_all",
    "load_accounts_file",
    "load_usage_file",
    "max_event_time",
    "parse_cents",
    "parse_instant",
    "paths",
    "profile_jsonl",
    "profile_landing_zone",
    "run_all",
    "run_pipeline",
    "table_count",
    "warehouse",
]
