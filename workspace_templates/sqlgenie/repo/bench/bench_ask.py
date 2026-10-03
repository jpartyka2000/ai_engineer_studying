#!/usr/bin/env python3
"""Measure what answering a question costs, in work rather than milliseconds.

Three numbers, none of them a wall clock:

``db_round_trips``
    Statements sent to PostgreSQL to answer one question. The floor is three -- the
    timeout, the tenant setting, and the query itself -- plus one connection for the API
    key lookup. A number that scales with anything is a per-request cost that will grow.

``catalog_queries``
    Times the service asked the database about its own schema while answering. Should be
    zero: the catalog is a Python dict, and re-deriving it per request is the classic way
    a text-to-SQL service becomes slow under load.

``rows_examined``
    Rows the plan reports visiting. Grows with the tenant's data, not with the number of
    tenants -- which is the property that makes a shared table safe to grow.

Wall-clock timings on a laptop running Docker are noise; a statement count is identical
on every machine and the gap between healthy and unhealthy is a factor of a hundred.
"""

from __future__ import annotations

import argparse
import json

from sqlgenie.config import MODEL, SETTINGS
from sqlgenie.db import pool
from sqlgenie.llm.recorded_client import RecordedClient
from sqlgenie.nl2sql import pipeline
from sqlgenie.tenancy import context

#: The question measured. An ordinary one, deliberately: the cost of the common path is
#: what matters, not the cost of the worst case.
QUESTION = "Who are our top 10 customers by total order value?"
TENANT = "acme"


class CountingCursor:
    """Wraps a cursor and counts the statements that pass through it."""

    def __init__(self, inner, counter: dict[str, int]) -> None:
        self._inner = inner
        self._counter = counter

    def execute(self, query, params=None, **kwargs):
        """Count, classify, then delegate."""
        self._counter["db_round_trips"] += 1
        lowered = str(query).lower()
        if "information_schema" in lowered or "pg_catalog" in lowered:
            self._counter["catalog_queries"] += 1
        return self._inner.execute(query, params, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __enter__(self):
        self._inner.__enter__()
        return self

    def __exit__(self, *args):
        return self._inner.__exit__(*args)


class CountingConnection:
    """Wraps a connection so every cursor it hands out is counted."""

    def __init__(self, inner, counter: dict[str, int]) -> None:
        self._inner = inner
        self._counter = counter

    def cursor(self, *args, **kwargs):
        """Return a counting cursor."""
        return CountingCursor(self._inner.cursor(*args, **kwargs), self._counter)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def main(argv: list[str] | None = None) -> int:
    """Answer one question with instrumentation and report the counts."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--json", action="store_true", help="suppress human-readable lines")
    args = parser.parse_args(argv)

    counter = {"db_round_trips": 0, "catalog_queries": 0}
    client = RecordedClient(SETTINGS.cassette_dir, model=MODEL)

    with context.bind_tenant(TENANT), pool.app_connection() as raw:
        counting = CountingConnection(raw, counter)
        answer = pipeline.ask(
            QUESTION,
            connection=counting,
            client=client,
            tenant_id=TENANT,
            max_rows=SETTINGS.max_rows,
            statement_timeout_ms=SETTINGS.statement_timeout_ms,
        )

        with raw.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (TENANT,))
            cursor.execute(
                f"EXPLAIN (ANALYZE, FORMAT JSON) {answer.executed_sql}",
                {"tenant_id": TENANT},
            )
            plan = cursor.fetchone()
            explained = list(plan.values())[0][0]["Plan"]

    measurement = {
        **counter,
        "rows_returned": answer.result.row_count,
        "predicates_added": answer.scoped.predicates_added,
        "rows_examined": int(explained.get("Actual Rows", 0)),
    }

    if not args.json:
        print(f"question         {QUESTION}")
        print(f"db round trips   {measurement['db_round_trips']}")
        print(f"catalog queries  {measurement['catalog_queries']}")
        print(f"predicates       {measurement['predicates_added']}")
        print(f"rows returned    {measurement['rows_returned']}")
        print()
    print(json.dumps(measurement, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
