"""The Mongo -> DuckDB pipeline.

The central test in this file is :func:`test_a_late_arrival_is_loaded_and_corrects_its
_bucket`. Everything else is scaffolding around it.

Events arrive late. A gateway buffering through a network partition delivers a
twenty-minute-old batch, and the minute those events belong to has already been rolled
up and reported. Whether the pipeline notices depends entirely on **which clock its
watermark runs on**: ingest time sees the batch arrive, event time has already moved
past the minute it belongs to and will never select it again. Both choices produce
perfectly plausible totals for the current window, which is why this needs a test rather
than a code review.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from eventstore import duck
from eventstore.ingest import ingest_events
from eventstore.models import EventIn
from eventstore.rollup import (
    EPOCH,
    LATE_ARRIVAL_THRESHOLD,
    get_position,
    rebuild_buckets,
    run_rollup,
)

pytestmark = pytest.mark.mongo

UTC = timezone.utc
#: 11:02:30 -- deliberately not on a minute boundary, so bucketing is actually tested.
BASE = datetime(2026, 4, 1, 11, 2, 30, tzinfo=UTC)
BUCKET = datetime(2026, 4, 1, 11, 2)  # naive UTC, as DuckDB stores it


def event(event_id: str, **overrides) -> EventIn:
    """Build a valid event, overriding only what a test cares about."""
    payload = {
        "event_id": event_id,
        "service": "checkout",
        "route": "/v1/checkout",
        "method": "POST",
        "status_code": 200,
        "latency_ms": 100.0,
        "region": "us-east-1",
        "occurred_at": BASE,
    }
    payload.update(overrides)
    return EventIn.model_validate(payload)


def bucket_row(connection, bucket=BUCKET):
    """Return the rollup row for one minute, or None."""
    return connection.execute(
        "SELECT requests, errors, sum_latency_ms, p50_ms, p95_ms, p99_ms, max_latency_ms "
        "FROM rollup_minute WHERE bucket = ? AND service = 'checkout' AND route = '/v1/checkout'",
        [bucket],
    ).fetchone()


def test_a_first_run_loads_everything_and_builds_its_buckets(events, warehouse) -> None:
    """Five requests at 100..500ms in one minute.

    p50 -> rank ceil(0.5*5) = 3 -> 300. p95 -> rank 5 -> 500. sum = 1500.
    """
    ingest_events(
        events,
        [event(f"evt-{n}", latency_ms=100.0 * n) for n in range(1, 6)],
        received_at=BASE + timedelta(seconds=2),
    )
    report = run_rollup(warehouse, events)

    assert report.events_loaded == 5
    assert report.buckets_rebuilt == 1
    assert duck.table_count(warehouse, "fact_requests") == 5

    requests, errors, total_latency, p50, p95, p99, maximum = bucket_row(warehouse)
    assert (requests, errors) == (5, 0)
    assert total_latency == 1500.0
    assert (p50, p95, p99, maximum) == (300.0, 500.0, 500.0, 500.0)


def test_errors_are_counted_in_the_rollup(events, warehouse) -> None:
    """Two 500s and one 404 among five: two errors, not three."""
    ingest_events(
        events,
        [event("a"), event("b", status_code=500), event("c", status_code=503),
         event("d", status_code=404), event("e")],
        received_at=BASE + timedelta(seconds=2),
    )
    run_rollup(warehouse, events)
    assert bucket_row(warehouse)[1] == 2


def test_the_watermark_advances_to_the_latest_ingest_time(events, warehouse) -> None:
    """Ingest time, not event time. The distinction is the subject of this module."""
    arrival = BASE + timedelta(seconds=2)
    ingest_events(events, [event("evt-1")], received_at=arrival)
    assert get_position(warehouse) == EPOCH

    report = run_rollup(warehouse, events)
    assert report.watermark == arrival
    assert get_position(warehouse) == arrival


def test_rerunning_does_not_double_count(events, warehouse) -> None:
    """The watermark is inclusive, so the boundary batch is re-read every run.

    That is harmless and deliberate: an exclusive watermark combined with a batch
    limit can cut a tie group in half and skip its remainder forever, while
    re-reading is free because the sink is keyed on ``event_id``. What must never
    change is the number of rows.
    """
    ingest_events(
        events, [event(f"evt-{n}") for n in range(5)], received_at=BASE + timedelta(seconds=2)
    )
    run_rollup(warehouse, events)
    second = run_rollup(warehouse, events)

    assert duck.table_count(warehouse, "fact_requests") == 5
    assert bucket_row(warehouse)[0] == 5
    assert second.events_loaded == 5  # re-read, not re-counted


def test_a_late_arrival_is_loaded_and_corrects_its_bucket(events, warehouse) -> None:
    """**The test this module exists for.**

    Three requests happen at 11:02 and are delivered two seconds later. **The stream
    then keeps flowing** -- a request at 11:12 arrives normally -- and the rollup runs.
    The 11:02 bucket says three requests.

    A fourth request *also happened at 11:02*, but its gateway was partitioned and
    delivers it at 11:29: twenty-seven minutes after the fact, and long after event
    time has moved on to 11:12.

    The second rollup must pick it up and the 11:02 bucket must become four requests.

    A watermark running on event time cannot do this: 11:02 is behind 11:12, so the
    document is never selected. Nothing fails, nothing is logged, and the 11:02 bucket
    reports three requests forever. The only visible symptom is that a number somebody
    exported last week no longer matches the number they export today.

    The "stream keeps flowing" part is not decoration. Without it both clocks give the
    same answer, because the late event's own minute is still the newest one either
    watermark has seen -- which is exactly why this bug survives a casual test.
    """
    ingest_events(
        events,
        [event(f"ontime-{n}") for n in range(3)],
        received_at=BASE + timedelta(seconds=2),
    )
    ingest_events(
        events,
        [event("later", occurred_at=BASE + timedelta(minutes=10))],
        received_at=BASE + timedelta(minutes=10, seconds=2),
    )
    run_rollup(warehouse, events)
    assert bucket_row(warehouse)[0] == 3

    ingest_events(
        events,
        [event("late-0", occurred_at=BASE, latency_ms=900.0)],
        received_at=BASE + timedelta(minutes=27),
    )
    report = run_rollup(warehouse, events)

    assert report.events_loaded >= 1
    assert report.late_events == 1
    assert report.oldest_event_loaded == BASE
    assert duck.table_count(warehouse, "fact_requests") == 5

    requests, _, _, _, _, _, maximum = bucket_row(warehouse)
    assert requests == 4, "the late event's own minute must be corrected, not the current one"
    assert maximum == 900.0


def test_lateness_is_measured_against_the_threshold(events, warehouse) -> None:
    """Two seconds is normal delivery; anything past the threshold is reported."""
    ingest_events(
        events, [event("prompt")], received_at=BASE + LATE_ARRIVAL_THRESHOLD
    )
    assert run_rollup(warehouse, events).late_events == 0

    ingest_events(
        events,
        [event("tardy", occurred_at=BASE + timedelta(seconds=1))],
        received_at=BASE + LATE_ARRIVAL_THRESHOLD + timedelta(seconds=30),
    )
    assert run_rollup(warehouse, events).late_events == 1


def test_a_late_event_in_a_different_minute_only_touches_that_minute(events, warehouse) -> None:
    """Correcting history must not disturb the buckets either side of it."""
    earlier = BASE - timedelta(minutes=5)
    ingest_events(
        events,
        [event("a", occurred_at=earlier), event("b"), event("c")],
        received_at=BASE + timedelta(seconds=2),
    )
    run_rollup(warehouse, events)
    assert bucket_row(warehouse)[0] == 2
    assert bucket_row(warehouse, datetime(2026, 4, 1, 10, 57))[0] == 1

    ingest_events(
        events,
        [event("late", occurred_at=earlier)],
        received_at=BASE + timedelta(minutes=30),
    )
    run_rollup(warehouse, events)

    assert bucket_row(warehouse, datetime(2026, 4, 1, 10, 57))[0] == 2
    assert bucket_row(warehouse)[0] == 2


def test_a_full_run_ignores_the_watermark(events, warehouse) -> None:
    """A warehouse is derived state; deleting it must be recoverable."""
    ingest_events(
        events, [event(f"evt-{n}") for n in range(4)], received_at=BASE + timedelta(seconds=2)
    )
    run_rollup(warehouse, events)
    warehouse.execute("DELETE FROM fact_requests")
    warehouse.execute("DELETE FROM rollup_minute")

    report = run_rollup(warehouse, events, full=True)
    assert report.events_loaded == 4
    assert bucket_row(warehouse)[0] == 4


def test_a_bucket_with_no_remaining_facts_is_removed(events, warehouse) -> None:
    """Otherwise an emptied minute keeps reporting the traffic it used to have."""
    ingest_events(
        events, [event("evt-0")], received_at=BASE + timedelta(seconds=2)
    )
    run_rollup(warehouse, events)
    assert bucket_row(warehouse) is not None

    warehouse.execute("DELETE FROM fact_requests")
    rebuild_buckets(warehouse, {(BUCKET, "checkout", "/v1/checkout")})
    assert bucket_row(warehouse) is None


def test_rebuilding_nothing_is_a_no_op(warehouse) -> None:
    assert rebuild_buckets(warehouse, []) == 0


def test_a_run_over_an_empty_collection_changes_nothing(events, warehouse) -> None:
    report = run_rollup(warehouse, events)
    assert report.events_loaded == 0
    assert report.buckets_rebuilt == 0
    assert get_position(warehouse) == EPOCH
