#!/usr/bin/env python
"""Measure how much work the reporting endpoints do.

Reports **query counts**, not wall-clock time. A count is what actually
distinguishes an N+1 from a single aggregate: it is deterministic, it does not care
how loaded the machine is, and the difference between 1 query and 200 is a signal no
amount of timing noise can obscure. Wall-clock timings are reported too, but only as
context.

Prints a single JSON object on the last line, which is the contract the grading
harness reads.

    python bench/bench_queries.py --json
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

from datetime import date, datetime, timezone  # noqa: E402

from django.db import connection, reset_queries  # noqa: E402
from django.test.utils import override_settings  # noqa: E402

from billing.models import LineItem  # noqa: E402
from projects.models import Project  # noqa: E402
from reporting.services import project_usage_summary  # noqa: E402
from tenants.models import Tenant  # noqa: E402

#: Enough projects that an N+1 is unmistakable but the setup stays fast.
PROJECT_COUNT = 40
ITEMS_PER_PROJECT = 5

PERIOD_START = date(2026, 3, 1)
PERIOD_END = date(2026, 3, 31)

BENCH_SLUG = "bench-tenant"


def seed() -> Tenant:
    """Create a throwaway tenant with enough projects to expose an N+1."""
    Tenant.objects.filter(slug=BENCH_SLUG).delete()
    tenant = Tenant.objects.create(
        name="Bench Tenant", slug=BENCH_SLUG, api_key="key-bench-9999", seat_count=50
    )
    for index in range(PROJECT_COUNT):
        project = Project.objects.create(
            tenant=tenant, name=f"Project {index:03d}", slug=f"project-{index:03d}"
        )
        LineItem.objects.bulk_create(
            [
                LineItem(
                    tenant=tenant,
                    project=project,
                    kind=LineItem.Kind.API_CALL,
                    description=f"usage {index}-{n}",
                    amount_cents=100 + n,
                    created_at=datetime(2026, 3, 1 + n, 12, tzinfo=timezone.utc),
                )
                for n in range(ITEMS_PER_PROJECT)
            ]
        )
    return tenant


def measure(tenant: Tenant) -> dict:
    """Run the summary and report how much work it took."""
    # DEBUG=True is what makes Django record executed SQL.
    with override_settings(DEBUG=True):
        reset_queries()
        started = time.perf_counter()
        rows = project_usage_summary(tenant.pk, PERIOD_START, PERIOD_END)
        elapsed_ms = (time.perf_counter() - started) * 1000
        queries = len(connection.queries)

    return {
        "queries": queries,
        "projects": len(rows),
        "elapsed_ms": round(elapsed_ms, 2),
        "line_items_total": sum(row.line_item_count for row in rows),
    }


def main() -> None:
    """Seed, measure, and print the result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print JSON only.")
    args = parser.parse_args()

    tenant = seed()
    try:
        result = measure(tenant)
    finally:
        Tenant.objects.filter(slug=BENCH_SLUG).delete()

    if not args.json:
        print(f"projects summarised : {result['projects']}")
        print(f"line items counted  : {result['line_items_total']}")
        print(f"SQL queries issued  : {result['queries']}")
        print(f"wall clock          : {result['elapsed_ms']} ms")
        print()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
