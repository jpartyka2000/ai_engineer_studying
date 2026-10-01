#!/usr/bin/env python
"""Measure how much work a pipeline run does.

Reports **operation counts** alongside the wall clock, and the counts are what should be held
to a threshold. Wall clock under Docker on a shared laptop varies by a factor of several; the
number of SQL statements the pipeline issues to load a batch does not.

The headline figure is ``statements_per_row``: how many DuckDB calls the whole run makes per
input row. It sits near two, because this pipeline inserts a row at a time into bronze and
again into silver. The absolute value is not the point -- what matters is that the figure
**does not grow with the size of the batch**. One that does is quadratic, and will look fine
on the sample data and die on a month of history.

    python bench/bench_pipeline.py --json
    python bench/bench_pipeline.py --events 4000

Volume is generated into a scratch directory by ``tools/gen_seed_data.py``, never into
``raw/``: the committed files are small on purpose and the suite asserts their exact counts.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import duckdb  # noqa: E402

from etlduck import connect, run_pipeline  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.gen_seed_data import generate  # noqa: E402

DEFAULT_EVENTS = 1_000
DEFAULT_DAYS = 2


class CountingConnection:
    """Wraps a DuckDB connection to count the statements issued through it.

    A proxy rather than a patched method, because ``execute`` is called on the connection
    object the pipeline holds -- patching the class would also count the statements the
    benchmark itself runs to read the results back.
    """

    def __init__(self, inner: duckdb.DuckDBPyConnection):
        self._inner = inner
        self.statements = 0

    def execute(self, *args, **kwargs):
        """Count and forward."""
        self.statements += 1
        return self._inner.execute(*args, **kwargs)

    def __getattr__(self, name: str):
        """Forward everything else untouched."""
        return getattr(self._inner, name)


def measure(events: int, days: int, seed: int = 20260301) -> dict:
    """Run the pipeline over generated volume and report the work done.

    The landing zone is generated into a temporary directory and removed afterwards, so the
    benchmark leaves nothing behind and cannot disturb the committed data.
    """
    scratch = Path(tempfile.mkdtemp(prefix="etlduck-bench-"))
    try:
        (scratch / "raw").mkdir()
        (scratch / "warehouse").mkdir()
        generate(
            scratch / "raw",
            accounts_count=8,
            days=days,
            events_per_day=events,
            seed=seed,
        )
        input_rows = sum(
            1
            for path in sorted((scratch / "raw").glob("usage_events_*.jsonl"))
            for _ in path.open(encoding="utf-8")
        )

        raw_connection = connect(scratch)
        counting = CountingConnection(raw_connection)
        try:
            started = time.perf_counter()
            result = run_pipeline(counting, scratch)
            elapsed_ms = (time.perf_counter() - started) * 1000
        finally:
            raw_connection.close()

        return {
            "input_rows": input_rows,
            "days": days,
            "events_per_day": events,
            "silver_rows": result.silver.rows_written if result.silver else 0,
            "gold_rows": result.gold.rows_written if result.gold else 0,
            "statements": counting.statements,
            "statements_per_row": round(counting.statements / input_rows, 4) if input_rows else 0.0,
            "elapsed_ms": round(elapsed_ms, 2),
            "us_per_row": round(elapsed_ms * 1000 / input_rows, 2) if input_rows else 0.0,
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    """Run the benchmark."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=DEFAULT_EVENTS, help="Events per day")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--json", action="store_true", help="Print JSON only.")
    args = parser.parse_args(argv)

    result = measure(args.events, args.days)
    if not args.json:
        print(f"input rows          : {result['input_rows']}")
        print(f"silver / gold rows  : {result['silver_rows']} / {result['gold_rows']}")
        print(f"SQL statements      : {result['statements']}")
        print(
            f"statements per row  : {result['statements_per_row']}  "
            "(should not grow with the batch size)"
        )
        print(f"wall clock          : {result['elapsed_ms']} ms ({result['us_per_row']} us/row)")
        print()
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
