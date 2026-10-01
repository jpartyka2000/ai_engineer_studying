#!/usr/bin/env python
"""Measure how much work profiling a table does.

Reports **operation counts** alongside the wall clock, and the counts are what should be
held to a threshold. Wall clock on a laptop under Docker varies by a factor of several
depending on what else is running; the number of times the profiler touches a cell does
not.

The headline figure is ``cell_reads_per_cell``: how many times each cell of the table is
examined over one ``profile_dataset`` call. It is a small constant for a profiler that
walks the table a fixed number of times, and grows with the column count for one that
re-walks it per column -- which is the difference between a profile that scales and one
that does not.

Prints a single JSON object on the last line, which is the contract the grading harness
reads.

    python bench/bench_profile.py --json
    python bench/bench_profile.py --rows 4000 --columns 24
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from edakit import profile as profile_module  # noqa: E402
from edakit import schema_infer  # noqa: E402

DEFAULT_ROWS = 2_000
DEFAULT_COLUMNS = 16


def synthetic_table(rows: int, columns: int) -> tuple[list[dict[str, str]], list[str]]:
    """Build a deterministic table with a realistic mix of column shapes.

    No RNG: the same arguments always produce the same table, so two runs of this
    benchmark are comparable. The mix matters -- a table of one column type would hide
    work done only on numeric or only on categorical columns.
    """
    names = [f"col_{index:02d}" for index in range(columns)]
    table: list[dict[str, str]] = []
    for row_index in range(rows):
        row: dict[str, str] = {}
        for column_index, name in enumerate(names):
            kind = column_index % 4
            if kind == 0:  # numeric, with the occasional hole
                row[name] = "" if row_index % 37 == 0 else str(row_index % 500)
            elif kind == 1:  # float
                row[name] = f"{(row_index % 311) / 7:.3f}"
            elif kind == 2:  # low-cardinality categorical
                row[name] = ("alpha", "beta", "gamma", "delta")[row_index % 4]
            else:  # boolean-ish
                row[name] = "true" if row_index % 3 else "false"
        table.append(row)
    return table, names


class Counter:
    """Wraps a function to count how often it is called."""

    def __init__(self, target):
        self.target = target
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self.target(*args, **kwargs)


def measure(rows: int, columns: int) -> dict:
    """Profile a synthetic table and report the work done.

    ``is_null`` is counted because every layer that walks the table goes through it --
    schema inference, the missing-value report and numeric extraction alike -- so it is
    a faithful proxy for "how many times was a cell looked at".
    """
    table, names = synthetic_table(rows, columns)

    counter = Counter(schema_infer.is_null)
    originals = {
        schema_infer: schema_infer.is_null,
        profile_module: profile_module.is_null,
    }
    # Patched in every module that imported the name directly, since `from x import y`
    # binds a new reference and patching only the source module would miss those.
    for module in originals:
        module.is_null = counter
    try:
        started = time.perf_counter()
        profile = profile_module.profile_dataset(table, names)
        elapsed_ms = (time.perf_counter() - started) * 1000
    finally:
        for module, original in originals.items():
            module.is_null = original

    cells = rows * columns
    return {
        "rows": rows,
        "columns": columns,
        "cells": cells,
        "profiled_columns": len(profile.columns),
        "cell_reads": counter.calls,
        "cell_reads_per_cell": round(counter.calls / cells, 4) if cells else 0.0,
        "elapsed_ms": round(elapsed_ms, 2),
    }


def main(argv: list[str] | None = None) -> int:
    """Run the benchmark."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--columns", type=int, default=DEFAULT_COLUMNS)
    parser.add_argument("--json", action="store_true", help="Print JSON only.")
    args = parser.parse_args(argv)

    result = measure(args.rows, args.columns)
    if not args.json:
        print(f"table                : {result['rows']} rows x {result['columns']} columns "
              f"({result['cells']} cells)")
        print(f"cell reads           : {result['cell_reads']}")
        print(f"reads per cell       : {result['cell_reads_per_cell']}  "
              "(a small constant; should not grow with the column count)")
        print(f"wall clock           : {result['elapsed_ms']} ms")
        print()
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
