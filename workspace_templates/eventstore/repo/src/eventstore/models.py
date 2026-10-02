"""The event schema, and the one place a timestamp becomes a datetime.

An event is one served HTTP request as the gateway saw it. Two timestamps, and the
difference between them is load-bearing:

``occurred_at``
    **Event time.** When the request happened, according to the gateway that served it.
    Every analytical question -- "what was p99 between 14:00 and 15:00" -- is asked in
    event time, because that is the only timeline a user experienced.

``received_at``
    **Ingest time.** When this service accepted the event. Set here, never by the
    client, because a clock we do not control must not be able to reorder our pipeline.
    Events arrive late: a gateway buffering through a network partition can deliver a
    twenty-minute-old batch, and ``received_at`` is how we notice.

**Timestamps are stored as BSON dates, never as strings.** A string timestamp compares
lexicographically in Mongo, which happens to agree with chronological order for one fixed
UTC offset format and silently disagrees for anything else -- and a range query over
mixed types matches whichever documents happen to share the type of the bound. The
validators below coerce every incoming timestamp to a timezone-aware UTC ``datetime``, so
there is exactly one representation in the collection.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Status codes at or above this count as errors for rate statistics. 4xx is excluded
#: on purpose: a client sending a malformed request is not this service failing, and
#: folding the two together makes an error-rate alert fire on someone else's bug.
ERROR_STATUS_FLOOR = 500


def to_utc(value: Any) -> datetime:
    """Coerce a timestamp to a timezone-aware UTC ``datetime``.

    Args:
        value: A ``datetime`` or an ISO-8601 string. A ``Z`` suffix is accepted.

    Returns:
        The same instant, timezone-aware, in UTC.

    Raises:
        ValueError: If the value is neither a datetime nor a parseable string, or if
            it is a naive datetime. A naive timestamp is rejected rather than assumed
            to be UTC: the assumption is right until one gateway is misconfigured, and
            then it is wrong by hours with nothing in the data to show it.
    """
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise ValueError(f"expected a datetime or ISO-8601 string, got {type(value).__name__}")
    if value.tzinfo is None:
        raise ValueError("timestamps must carry a timezone; naive values are rejected")
    return value.astimezone(timezone.utc)


class EventIn(BaseModel):
    """One request event as a client submits it.

    ``received_at`` is deliberately absent: it is stamped on ingest.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=64, description="Client-generated, unique")
    service: str = Field(min_length=1, max_length=64)
    route: str = Field(min_length=1, max_length=200)
    method: str = Field(default="GET", max_length=10)
    status_code: int = Field(ge=100, le=599)
    latency_ms: float = Field(ge=0, le=600_000)
    region: str = Field(default="us-east-1", max_length=32)
    occurred_at: datetime

    @field_validator("occurred_at", mode="before")
    @classmethod
    def _normalise_occurred_at(cls, value: Any) -> datetime:
        """Reject naive timestamps and normalise everything else to UTC."""
        return to_utc(value)

    @property
    def is_error(self) -> bool:
        """Whether this event counts towards the error rate."""
        return self.status_code >= ERROR_STATUS_FLOOR

    def to_document(self, received_at: datetime) -> dict[str, Any]:
        """Render the event as the Mongo document to insert.

        Args:
            received_at: Ingest timestamp, stamped by the server.

        Returns:
            A dict with BSON-native types throughout.
        """
        return {
            "event_id": self.event_id,
            "service": self.service,
            "route": self.route,
            "method": self.method,
            "status_code": self.status_code,
            "latency_ms": float(self.latency_ms),
            "region": self.region,
            "occurred_at": self.occurred_at,
            "received_at": to_utc(received_at),
            "is_error": self.is_error,
        }


class ExportedEvent(EventIn):
    """An event replayed from a historical export.

    The only difference from :class:`EventIn` is that this one **may** carry its
    original ``received_at``, and the distinction is deliberate. Over HTTP the ingest
    time is ours to stamp: a client that can set it can reorder our pipeline, and
    :class:`EventIn` forbids the field outright. A backfill is the opposite case --
    the original ingest times are a fact about what happened and throwing them away
    would make every replayed event look like it arrived on time, erasing exactly the
    lateness the pipeline exists to handle.
    """

    received_at: datetime | None = None

    @field_validator("received_at", mode="before")
    @classmethod
    def _normalise_received_at(cls, value: Any) -> datetime | None:
        """Allow an absent ingest time; normalise anything present to UTC."""
        return None if value is None else to_utc(value)


class IngestRequest(BaseModel):
    """A batch of events.

    Batched because the gateway emits thousands per second and one HTTP round trip per
    request event would cost more than serving the request did.
    """

    model_config = ConfigDict(extra="forbid")

    events: list[EventIn] = Field(min_length=1, max_length=1000)


class IngestResult(BaseModel):
    """What one ingest call did.

    ``duplicates`` is a success, not an error: a gateway that retries a batch after a
    timeout is behaving correctly, and the second delivery must be absorbed silently.
    """

    received: int
    inserted: int
    duplicates: int
    watermark: datetime | None = Field(
        default=None, description="Latest occurred_at in the accepted batch"
    )


class EventOut(BaseModel):
    """An event as the read endpoints return it."""

    model_config = ConfigDict(extra="ignore")

    event_id: str
    service: str
    route: str
    method: str
    status_code: int
    latency_ms: float
    region: str
    occurred_at: datetime
    received_at: datetime

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> EventOut:
        """Build from a Mongo document, dropping ``_id`` and any derived fields."""
        return cls.model_validate({k: v for k, v in document.items() if k != "_id"})
