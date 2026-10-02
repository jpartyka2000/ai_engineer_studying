"""The event schema.

Most of these tests are about **one decision**: that a timestamp without a timezone is
rejected rather than assumed to be UTC. The assumption is correct until one gateway is
misconfigured, and then it is wrong by hours with nothing in the data to show it -- the
events are simply filed under times they did not happen at, and every percentile,
baseline and rollup computed from them is quietly wrong.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from eventstore.models import ERROR_STATUS_FLOOR, EventIn, EventOut, ExportedEvent, to_utc

UTC = timezone.utc
OCCURRED = datetime(2026, 4, 1, 11, 30, tzinfo=UTC)


def make(**overrides) -> EventIn:
    """Build a valid event, overriding only what a test cares about."""
    payload = {
        "event_id": "evt-000001",
        "service": "checkout",
        "route": "/v1/checkout",
        "method": "POST",
        "status_code": 200,
        "latency_ms": 123.4,
        "region": "us-east-1",
        "occurred_at": OCCURRED,
    }
    payload.update(overrides)
    return EventIn.model_validate(payload)


def test_a_naive_timestamp_is_rejected() -> None:
    """No timezone, no event. The alternative is silently wrong data."""
    with pytest.raises(ValidationError, match="timezone"):
        make(occurred_at=datetime(2026, 4, 1, 11, 30))
    with pytest.raises(ValidationError, match="timezone"):
        make(occurred_at="2026-04-01T11:30:00")


def test_a_z_suffix_is_accepted() -> None:
    """Gateways emit RFC-3339 with a Z, which ``fromisoformat`` needs help with."""
    assert make(occurred_at="2026-04-01T11:30:00Z").occurred_at == OCCURRED


def test_a_non_utc_offset_is_converted_not_stored() -> None:
    """09:30+02:00 is the same instant as 07:30Z, and that is how it must be stored.

    One representation in the collection means a range query cannot match some events
    and miss others that happened at the same moment.
    """
    event = make(occurred_at="2026-04-01T09:30:00+02:00")
    assert event.occurred_at == datetime(2026, 4, 1, 7, 30, tzinfo=UTC)
    assert event.occurred_at.tzinfo == UTC


def test_to_utc_rejects_things_that_are_not_timestamps() -> None:
    with pytest.raises(ValueError, match="expected a datetime"):
        to_utc(1743500000)


def test_a_client_may_not_set_the_ingest_time() -> None:
    """``received_at`` over HTTP is ours to stamp.

    A client that can set it can reorder our pipeline: the rollup's watermark moves in
    ingest time, so a gateway sending ``received_at`` far in the future would push the
    watermark past every event that follows.
    """
    with pytest.raises(ValidationError, match="received_at"):
        make(received_at="2026-04-01T11:30:02Z")


def test_an_export_may_carry_its_original_ingest_time() -> None:
    """A backfill is the opposite case: the original ingest times are a fact.

    Discarding them would make every replayed event look like it arrived on time,
    erasing exactly the lateness the pipeline exists to handle.
    """
    event = ExportedEvent.model_validate(
        {
            "event_id": "evt-000002",
            "service": "checkout",
            "route": "/v1/checkout",
            "status_code": 200,
            "latency_ms": 10.0,
            "occurred_at": "2026-04-01T11:30:00Z",
            "received_at": "2026-04-01T11:55:00Z",
        }
    )
    assert event.received_at == OCCURRED + timedelta(minutes=25)
    assert ExportedEvent.model_validate({**event.model_dump(), "received_at": None}).received_at is None


def test_only_server_errors_count_as_errors() -> None:
    """4xx is somebody else's bug.

    Folding client errors into the error rate makes an alert fire when a caller ships
    a malformed request, which trains everyone to ignore the alert.
    """
    assert ERROR_STATUS_FLOOR == 500
    assert make(status_code=500).is_error is True
    assert make(status_code=503).is_error is True
    assert make(status_code=499).is_error is False
    assert make(status_code=404).is_error is False


def test_to_document_emits_bson_native_types() -> None:
    """Timestamps as datetimes, never strings.

    A string timestamp compares lexicographically in Mongo, which agrees with
    chronological order for one fixed format and silently disagrees for any other --
    and a range query over mixed types matches only documents sharing the bound's type.
    """
    received = OCCURRED + timedelta(seconds=2)
    document = make().to_document(received)
    assert isinstance(document["occurred_at"], datetime)
    assert isinstance(document["received_at"], datetime)
    assert document["occurred_at"].tzinfo == UTC
    assert document["received_at"] == received
    assert document["is_error"] is False
    assert "_id" not in document


def test_to_document_normalises_a_received_at_with_an_offset() -> None:
    document = make().to_document(datetime(2026, 4, 1, 13, 30, tzinfo=timezone(timedelta(hours=2))))
    assert document["received_at"] == datetime(2026, 4, 1, 11, 30, tzinfo=UTC)


def test_field_bounds_are_enforced() -> None:
    with pytest.raises(ValidationError):
        make(status_code=99)
    with pytest.raises(ValidationError):
        make(status_code=600)
    with pytest.raises(ValidationError):
        make(latency_ms=-1.0)
    with pytest.raises(ValidationError):
        make(event_id="")


def test_unknown_fields_are_rejected() -> None:
    """A typo in a producer should fail loudly rather than be dropped on the floor."""
    with pytest.raises(ValidationError):
        make(latency_millis=5.0)


def test_event_out_drops_the_mongo_id() -> None:
    document = make().to_document(OCCURRED)
    out = EventOut.from_document({"_id": "abc", **document})
    assert out.event_id == "evt-000001"
    assert not hasattr(out, "_id")
