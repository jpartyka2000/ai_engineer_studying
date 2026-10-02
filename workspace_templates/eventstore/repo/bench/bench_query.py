#!/usr/bin/env python3
"""Measure how much work the recent-window query makes the server do.

**Documents examined, not milliseconds.** A wall-clock number on a laptop running three
other containers tells you about the laptop. ``totalDocsExamined`` is what the server
actually had to look at, it is identical on every machine, and the gap between a healthy
value and an unhealthy one here is a factor of a hundred rather than a factor of two.

The query under test is the one ``/v1/events/recent`` runs: equality on ``service``, a
descending range on ``occurred_at``, and a limit. Served by the ``service_occurred_at``
index the server walks the index in order and stops at the limit, so it examines about
as many documents as it returns. Anything that stops the index from satisfying the sort
-- dropping it, reordering its keys, or sorting on a different field -- forces the
server to fetch every document in the window and order them in memory, and this number
goes from a hundred to the size of the window.

Run it with ``make bench``. The JSON on the last line is what the grading harness reads.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone

from eventstore import mongo, queries
from eventstore.config import Settings
from eventstore.models import EventIn

#: Scratch database. Dropped before and after, so a run never touches real data.
BENCH_DATABASE = "eventstore_bench"

#: Services the synthetic traffic is spread across. More than one, because a query
#: whose equality field matches every document in the collection cannot show the
#: difference between an index walk and a scan.
SERVICES = ["checkout", "catalog", "auth", "search"]

#: A full day, which is the widest window the endpoint allows, against the default
#: limit. The width is the point: with a narrow window the matched set is already
#: smaller than the limit, so an index that cannot satisfy the sort costs nothing and
#: the measurement shows nothing. Here the window holds thousands of events and the
#: caller wants a hundred, so "walk the index and stop" and "fetch everything, then
#: sort, then take a hundred" differ by a factor of fifty.
WINDOW_MINUTES = 1440
LIMIT = 100


def populate(collection, total: int, now: datetime) -> None:
    """Insert ``total`` synthetic events spread over a day across four services."""
    documents = []
    for index in range(total):
        occurred_at = now - timedelta(seconds=(index * 86400) / total)
        event = EventIn(
            event_id=f"bench-{index:08d}",
            service=SERVICES[index % len(SERVICES)],
            route="/v1/checkout",
            method="POST",
            status_code=200 if index % 97 else 500,
            latency_ms=50.0 + (index % 400),
            region="us-east-1",
            occurred_at=occurred_at,
        )
        documents.append(event.to_document(occurred_at + timedelta(seconds=2)))
    collection.insert_many(documents, ordered=False)


def main(argv: list[str] | None = None) -> int:
    """Populate a scratch collection, explain the query, print the measurement."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--events", type=int, default=20_000, help="synthetic collection size")
    parser.add_argument("--json", action="store_true", help="suppress the human-readable lines")
    args = parser.parse_args(argv)

    now = datetime(2026, 4, 2, 0, 0, tzinfo=timezone.utc)
    client = mongo.get_client(Settings())
    try:
        client.drop_database(BENCH_DATABASE)
        collection = client[BENCH_DATABASE][mongo.EVENTS_COLLECTION]
        mongo.ensure_indexes(collection)
        populate(collection, args.events, now)

        plan = queries.explain_recent(
            collection, "checkout", minutes=WINDOW_MINUTES, limit=LIMIT, now=now
        )
        in_window = collection.count_documents(
            {
                "service": "checkout",
                "occurred_at": {"$gte": now - timedelta(minutes=WINDOW_MINUTES), "$lt": now},
            }
        )
    finally:
        client.drop_database(BENCH_DATABASE)
        client.close()

    returned = max(plan["docs_returned"], 1)
    measurement = {
        "collection_size": args.events,
        "events_in_window": in_window,
        "docs_examined": plan["docs_examined"],
        "keys_examined": plan["keys_examined"],
        "docs_returned": plan["docs_returned"],
        "examined_per_returned": round(plan["docs_examined"] / returned, 3),
        "used_index": 0 if plan["index_name"] is None else 1,
        "sort_in_memory": plan["sort_in_memory"],
    }

    if not args.json:
        print(f"collection      {args.events} events across {len(SERVICES)} services")
        print(f"window          {WINDOW_MINUTES} minutes, limit {LIMIT}")
        print(f"in window       {in_window} events for checkout")
        print(f"plan            {plan['stage']} via {plan['index_name'] or 'NO INDEX'}")
        print(f"sorted in RAM   {'yes' if plan['sort_in_memory'] else 'no'}")
        print(f"examined        {plan['docs_examined']} documents")
        print(f"returned        {plan['docs_returned']} documents")
        print(f"ratio           {measurement['examined_per_returned']} examined per returned")
        print()
    print(json.dumps(measurement, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
