"""The write path.

Every test here is about the same question in a different disguise: **what happens when
the gateway sends us something twice?** It does, constantly -- a timeout on its side is
a retry, and a retry is a duplicate batch. A pipeline that cannot absorb one reports
double the traffic and half the error rate the next morning.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pymongo import ASCENDING

from eventstore import mongo
from eventstore.ingest import DUPLICATE_KEY, group_by_arrival, ingest_events, parse_batch, utcnow
from eventstore.models import EventIn, ExportedEvent

pytestmark = pytest.mark.mongo

UTC = timezone.utc
OCCURRED = datetime(2026, 4, 1, 11, 30, tzinfo=UTC)


def event(event_id: str, **overrides) -> EventIn:
    """Build a valid event, overriding only what a test cares about."""
    payload = {
        "event_id": event_id,
        "service": "checkout",
        "route": "/v1/checkout",
        "method": "POST",
        "status_code": 200,
        "latency_ms": 120.0,
        "region": "us-east-1",
        "occurred_at": OCCURRED,
    }
    payload.update(overrides)
    return EventIn.model_validate(payload)


def test_a_batch_is_inserted(events) -> None:
    result = ingest_events(events, [event(f"evt-{n}") for n in range(5)])
    assert (result.received, result.inserted, result.duplicates) == (5, 5, 0)
    assert events.count_documents({}) == 5


def test_a_retried_batch_is_absorbed_without_double_counting(events) -> None:
    """**The test that matters.**

    The same five events are delivered twice. The second delivery must insert nothing,
    report five duplicates, and leave the collection at five documents. This is
    enforced by the unique index, not by the application: a read-then-write check is a
    race, and two workers replaying the same batch would both see "absent".
    """
    batch = [event(f"evt-{n}") for n in range(5)]
    ingest_events(events, batch)
    second = ingest_events(events, batch)

    assert second.received == 5
    assert second.inserted == 0
    assert second.duplicates == 5
    assert events.count_documents({}) == 5


def test_a_partially_overlapping_batch_inserts_only_the_new_events(events) -> None:
    """Unordered inserts, so a duplicate in the middle does not block what follows.

    With ``ordered=True`` Mongo stops at the first error: events 2, 3 and 4 would be
    silently dropped while the call reported success for the batch.
    """
    ingest_events(events, [event("evt-0"), event("evt-1")])
    result = ingest_events(events, [event(f"evt-{n}") for n in range(5)])

    assert result.inserted == 3
    assert result.duplicates == 2
    assert events.count_documents({}) == 5
    assert {doc["event_id"] for doc in events.find({}, {"event_id": 1})} == {
        f"evt-{n}" for n in range(5)
    }


def test_the_whole_batch_shares_one_ingest_time(events) -> None:
    """They arrived in one delivery; microsecond-apart stamps would imply an ordering
    the network never provided, and the rollup's watermark moves in ingest time."""
    stamp = utcnow()
    ingest_events(events, [event(f"evt-{n}") for n in range(4)], received_at=stamp)
    stamps = {doc["received_at"] for doc in events.find({}, {"received_at": 1})}
    assert len(stamps) == 1


def test_the_watermark_is_the_latest_event_time_in_the_batch(events) -> None:
    """Event time, not ingest time: this is what a producer tracks its own progress by."""
    latest = OCCURRED + timedelta(minutes=9)
    batch = [
        event("evt-a", occurred_at=OCCURRED),
        event("evt-b", occurred_at=latest),
        event("evt-c", occurred_at=OCCURRED + timedelta(minutes=3)),
    ]
    assert ingest_events(events, batch).watermark == latest


def test_an_empty_batch_is_an_error(events) -> None:
    with pytest.raises(ValueError, match="empty batch"):
        ingest_events(events, [])


def test_documents_are_stored_with_bson_dates(events) -> None:
    """Not strings. A mixed-type range query matches only one of the two types."""
    ingest_events(events, [event("evt-0")])
    document = events.find_one({"event_id": "evt-0"})
    assert isinstance(document["occurred_at"], datetime)
    assert isinstance(document["received_at"], datetime)
    assert document["is_error"] is False


def test_ensure_indexes_creates_a_unique_dedupe_index(bare_events) -> None:
    """Asserted on a collection where ``ensure_indexes`` has not already run.

    The uniqueness of ``event_id`` is the only thing standing between a retried batch
    and a doubled revenue number, so it is asserted directly rather than inferred from
    the behaviour of an insert.
    """
    names = mongo.ensure_indexes(bare_events)
    information = bare_events.index_information()

    assert set(names) == {"event_id_unique", "service_occurred_at", "received_at"}
    assert information["event_id_unique"]["unique"] is True
    assert information["event_id_unique"]["key"] == [("event_id", ASCENDING)]
    assert information["service_occurred_at"]["key"] == [("service", 1), ("occurred_at", -1)]
    assert not information["service_occurred_at"].get("unique", False)


def test_ensure_indexes_is_idempotent(events) -> None:
    """A job restarted twice a minute must not fail on its own start-up."""
    before = mongo.ensure_indexes(events)
    assert mongo.ensure_indexes(events) == before


def test_the_duplicate_key_code_is_the_one_mongo_sends(events) -> None:
    """Pinned so that a refactor cannot quietly start swallowing a different error."""
    ingest_events(events, [event("evt-0")])
    from pymongo.errors import BulkWriteError

    with pytest.raises(BulkWriteError) as caught:
        events.insert_many([event("evt-0").to_document(utcnow())], ordered=True)
    assert caught.value.details["writeErrors"][0]["code"] == DUPLICATE_KEY


# ---------------------------------------------------------------------------
# export parsing, which needs no database
# ---------------------------------------------------------------------------


def test_parse_batch_accepts_an_exported_ingest_time() -> None:
    rows = [
        {
            "event_id": "evt-0",
            "service": "checkout",
            "route": "/v1/checkout",
            "status_code": 200,
            "latency_ms": 10.0,
            "occurred_at": "2026-04-01T11:30:00Z",
            "received_at": "2026-04-01T11:55:00Z",
        }
    ]
    parsed = parse_batch(rows)
    assert isinstance(parsed[0], ExportedEvent)
    assert parsed[0].received_at == OCCURRED + timedelta(minutes=25)


def test_group_by_arrival_replays_the_original_batches() -> None:
    """A backfill is a replay of deliveries, oldest first -- not one undifferentiated
    dump -- so that the rollup's ingest-time watermark advances as it originally did."""
    early = OCCURRED + timedelta(seconds=2)
    late = OCCURRED + timedelta(minutes=25)
    default = OCCURRED + timedelta(hours=1)
    rows = [
        ExportedEvent.model_validate({**event("evt-0").model_dump(), "received_at": late}),
        ExportedEvent.model_validate({**event("evt-1").model_dump(), "received_at": early}),
        ExportedEvent.model_validate({**event("evt-2").model_dump(), "received_at": early}),
        ExportedEvent.model_validate({**event("evt-3").model_dump(), "received_at": None}),
    ]
    grouped = group_by_arrival(rows, default_received_at=default)

    assert [moment for moment, _ in grouped] == [early, late, default]
    assert [len(batch) for _, batch in grouped] == [2, 1, 1]
