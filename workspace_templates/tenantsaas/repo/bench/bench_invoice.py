#!/usr/bin/env python
"""Measure how much data invoice totalling pulls out of the database.

Reports **rows fetched**, not wall-clock time, and not query count either.

Query count is the right metric for an N+1 (see ``bench_queries.py``), but it is blind
to this class of problem: summing a million line items in Python is *one* query. What
scales here is the number of rows crossing the wire and being turned into Python
objects, so that is what this measures. A total is three numbers; if computing it costs
one row per line item, cost grows with the customer's usage forever.

Measured at two data sizes so the *shape* is visible rather than a single number:
a fix that is merely faster still fetches more rows as usage grows, while a fix that
aggregates in SQL fetches the same handful either way.

Prints a single JSON object on the last line, which is the contract the grading
harness reads.

    python bench/bench_invoice.py --json
"""

import argparse
import json
import os
import sys
import time

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from datetime import date, datetime, timedelta, timezone  # noqa: E402

from django.db import connection, reset_queries  # noqa: E402
from django.test.utils import override_settings  # noqa: E402

from billing.models import LineItem  # noqa: E402
from billing.services import compute_totals  # noqa: E402
from projects.models import Project  # noqa: E402
from tenants.models import Tenant  # noqa: E402

#: Two sizes an order of magnitude apart. Both small enough to seed in seconds; far
#: enough apart that a per-row cost is unmistakable rather than arguable.
SMALL_ITEMS = 250
LARGE_ITEMS = 5_000

PERIOD_START = date(2026, 3, 1)
PERIOD_END = date(2026, 3, 31)

SMALL_SLUG = "bench-invoice-small"
LARGE_SLUG = "bench-invoice-large"


def seed(slug: str, item_count: int) -> Tenant:
    """Create a throwaway tenant with ``item_count`` line items inside the period."""
    Tenant.objects.filter(slug=slug).delete()
    tenant = Tenant.objects.create(
        name=f"Bench {slug}", slug=slug, api_key=f"key-{slug}", seat_count=50
    )
    project = Project.objects.create(tenant=tenant, name="Bench", slug="bench")
    start = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
    LineItem.objects.bulk_create(
        [
            LineItem(
                tenant=tenant,
                project=project,
                kind=LineItem.Kind.CREDIT if index % 50 == 49 else LineItem.Kind.API_CALL,
                description=f"usage {index}",
                amount_cents=-100 if index % 50 == 49 else 100 + (index % 7),
                # Spread across the period but never past its end, so every row is
                # inside the window being totalled.
                created_at=start + timedelta(minutes=(index % (30 * 24 * 60))),
            )
            for index in range(item_count)
        ],
        batch_size=1_000,
    )
    return tenant


def measure(tenant: Tenant) -> dict:
    """Total one tenant's period and report the work it cost.

    Rows are counted through ``connection.execute_wrapper``, reading ``cursor.rowcount``
    after each statement. That is the driver's own count of the result set, so it does
    not care how the ORM was used or whether the rows were later discarded.
    """
    fetched = 0

    def count_rows(execute, sql, params, many, context):
        nonlocal fetched
        result = execute(sql, params, many, context)
        cursor = context.get("cursor")
        rowcount = getattr(cursor, "rowcount", -1) or 0
        # Only SELECTs return rows; rowcount is -1 or 0 for the rest.
        if rowcount > 0 and sql.lstrip().upper().startswith("SELECT"):
            fetched += rowcount
        return result

    with override_settings(DEBUG=True):
        reset_queries()
        started = time.perf_counter()
        with connection.execute_wrapper(count_rows):
            totals = compute_totals(tenant.pk, PERIOD_START, PERIOD_END)
        elapsed_ms = (time.perf_counter() - started) * 1000
        queries = len(connection.queries)

    return {
        "rows_fetched": fetched,
        "queries": queries,
        "line_items_counted": totals.line_item_count,
        "total_cents": totals.total_cents,
        "elapsed_ms": round(elapsed_ms, 2),
    }


def main() -> None:
    """Seed both sizes, measure each, and print the comparison."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print JSON only.")
    args = parser.parse_args()

    try:
        small = measure(seed(SMALL_SLUG, SMALL_ITEMS))
        large = measure(seed(LARGE_SLUG, LARGE_ITEMS))
    finally:
        Tenant.objects.filter(slug__in=[SMALL_SLUG, LARGE_SLUG]).delete()

    result = {
        "items_small": SMALL_ITEMS,
        "items_large": LARGE_ITEMS,
        "rows_small": small["rows_fetched"],
        "rows_large": large["rows_fetched"],
        "queries_small": small["queries"],
        "queries_large": large["queries"],
        # The headline number: how much more data the larger tenant costs. 1.0 means
        # the cost is independent of usage, which is the whole point.
        "rows_growth": round(large["rows_fetched"] / max(small["rows_fetched"], 1), 2),
        "elapsed_ms_large": large["elapsed_ms"],
        "line_items_counted_large": large["line_items_counted"],
    }

    if not args.json:
        print(f"small tenant  : {SMALL_ITEMS:>6} items -> {small['rows_fetched']:>6} rows fetched")
        print(f"large tenant  : {LARGE_ITEMS:>6} items -> {large['rows_fetched']:>6} rows fetched")
        print(f"growth factor : {result['rows_growth']}  (1.0 = independent of usage)")
        print(f"queries       : {small['queries']} small, {large['queries']} large")
        print()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
