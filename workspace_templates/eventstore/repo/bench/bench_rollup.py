#!/usr/bin/env python3
"""Measure whether an incremental rollup stays proportional to what arrived.

The property worth defending: **running the rollup twice in a row must be cheap.** The
first run consumes the backlog; the second should find almost nothing, because the
watermark has moved. A rollup whose second run costs the same as its first is one that
re-reads the whole collection every time, and that cost grows with the age of the
service rather than with its traffic.

The number reported is ``second_run_loaded`` -- documents the second run pulled out of
Mongo. It is not zero by design: the watermark is inclusive, so the final ingest batch
is always re-read. It should be a batch, not a backlog.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone

from eventstore import duck, mongo
from eventstore.config import Settings
from eventstore.models import EventIn
from eventstore.rollup import run_rollup

BENCH_DATABASE = "eventstore_bench_rollup"
#: Events per simulated delivery, so the inclusive-watermark re-read has a known size.
BATCH_SIZE = 50


def main(argv: list[str] | None = None) -> int:
    """Load synthetic deliveries, roll up twice, report what each run cost."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--batches", type=int, default=40, help="simulated deliveries")
    parser.add_argument("--json", action="store_true", help="suppress human-readable lines")
    args = parser.parse_args(argv)

    start = datetime(2026, 4, 1, 11, 0, tzinfo=timezone.utc)
    settings = Settings(mongo_database=BENCH_DATABASE)
    client = mongo.get_client(settings)
    connection = duck.connect_path("/tmp/eventstore-bench-rollup.duckdb")
    try:
        client.drop_database(BENCH_DATABASE)
        collection = client[BENCH_DATABASE][mongo.EVENTS_COLLECTION]
        mongo.ensure_indexes(collection)
        connection.execute("DELETE FROM fact_requests")
        connection.execute("DELETE FROM rollup_minute")
        connection.execute("DELETE FROM rollup_state")

        for batch in range(args.batches):
            arrival = start + timedelta(minutes=batch, seconds=2)
            documents = [
                EventIn(
                    event_id=f"bench-{batch:04d}-{index:04d}",
                    service="checkout",
                    route="/v1/checkout",
                    method="POST",
                    status_code=200,
                    latency_ms=100.0 + index,
                    region="us-east-1",
                    occurred_at=start + timedelta(minutes=batch, seconds=index % 60),
                ).to_document(arrival)
                for index in range(BATCH_SIZE)
            ]
            collection.insert_many(documents, ordered=False)

        first = run_rollup(connection, collection)
        second = run_rollup(connection, collection)
        total = collection.count_documents({})
    finally:
        client.drop_database(BENCH_DATABASE)
        client.close()
        connection.close()

    measurement = {
        "collection_size": total,
        "first_run_loaded": first.events_loaded,
        "second_run_loaded": second.events_loaded,
        "buckets_rebuilt_first": first.buckets_rebuilt,
        "buckets_rebuilt_second": second.buckets_rebuilt,
        "rescan_fraction": round(second.events_loaded / max(total, 1), 4),
    }

    if not args.json:
        print(f"collection      {total} events in {args.batches} deliveries")
        print(f"first run       loaded {first.events_loaded}, rebuilt {first.buckets_rebuilt}")
        print(f"second run      loaded {second.events_loaded}, rebuilt {second.buckets_rebuilt}")
        print(f"rescan          {measurement['rescan_fraction']:.2%} of the collection")
        print()
    print(json.dumps(measurement, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
