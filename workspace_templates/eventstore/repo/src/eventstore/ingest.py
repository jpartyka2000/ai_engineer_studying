"""The write path.

One job: get a validated batch into the operational store exactly once, quickly, and
without letting one bad event reject the other nine hundred and ninety-nine.

**Deduplication is the unique index, not a lookup.** The obvious implementation --
query for the ids already present, then insert the rest -- is a race: two workers
replaying the same retried batch both see "absent" and both insert. Here every batch is
inserted unordered and duplicate-key errors are *counted* rather than raised. The
database arbitrates, which is the only component that can.

**Unordered matters.** With ``ordered=True`` Mongo stops at the first error, so a single
duplicate in position three silently drops everything after it while reporting success
for the batch. With ``ordered=False`` every insertable document is inserted and the
errors come back together.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, Sequence

from pymongo.collection import Collection
from pymongo.errors import BulkWriteError

from eventstore.models import EventIn, ExportedEvent, IngestResult

logger = logging.getLogger(__name__)

#: Mongo's duplicate-key error code. Named because the bare 11000 in an exception
#: handler is the kind of constant nobody can look up during an incident.
DUPLICATE_KEY = 11000


def utcnow() -> datetime:
    """Return the current instant, timezone-aware, in UTC.

    Wrapped so that tests can pass an explicit ``received_at`` instead and so that no
    module in this package is tempted to call ``datetime.now()`` without a timezone.
    """
    return datetime.now(timezone.utc)


def ingest_events(
    collection: Collection,
    events: Sequence[EventIn],
    *,
    received_at: datetime | None = None,
) -> IngestResult:
    """Insert a batch of events, absorbing duplicates.

    Args:
        collection: The events collection.
        events: Validated events.
        received_at: Ingest timestamp to stamp on every document in the batch. One
            timestamp for the whole batch, not one per document: they arrived in the
            same delivery, and giving them microsecond-apart ingest times would imply
            an ordering the network never provided.

    Returns:
        An :class:`~eventstore.models.IngestResult`. ``watermark`` is the greatest
        ``occurred_at`` in the submitted batch, which is what a caller tracking its own
        delivery progress needs.

    Raises:
        ValueError: If the batch is empty.
    """
    if not events:
        raise ValueError("cannot ingest an empty batch")

    stamp = received_at or utcnow()
    documents = [event.to_document(stamp) for event in events]

    inserted = 0
    duplicates = 0
    try:
        result = collection.insert_many(documents, ordered=False)
        inserted = len(result.inserted_ids)
    except BulkWriteError as exc:
        write_errors = exc.details.get("writeErrors", [])
        duplicates = sum(1 for error in write_errors if error.get("code") == DUPLICATE_KEY)
        unexpected = [error for error in write_errors if error.get("code") != DUPLICATE_KEY]
        inserted = exc.details.get("nInserted", 0)
        if unexpected:
            # Anything that is not a duplicate is a real failure and must surface.
            # Swallowing it here is how a schema problem becomes "ingest looks fine,
            # the numbers are just low".
            logger.error("ingest failed for %d document(s)", len(unexpected))
            raise

    # Debug rather than info: a backfill replays hundreds of deliveries and one line
    # each buries the summary the caller actually reports.
    logger.debug("ingested %d event(s), %d duplicate(s)", inserted, duplicates)
    return IngestResult(
        received=len(events),
        inserted=inserted,
        duplicates=duplicates,
        watermark=max(event.occurred_at for event in events),
    )


def parse_batch(rows: Iterable[dict]) -> list[ExportedEvent]:
    """Validate raw dicts from an export into events.

    Args:
        rows: Decoded JSON objects, e.g. the lines of a ``.jsonl`` export.

    Returns:
        Validated events, in input order. Each may carry its original
        ``received_at``; see :class:`~eventstore.models.ExportedEvent` for why that is
        allowed here and forbidden over HTTP.

    Raises:
        pydantic.ValidationError: On the first unusable row. The loader is strict on
            purpose: a malformed export should stop the load and be investigated, not
            be partially absorbed into numbers somebody will later report.
    """
    return [ExportedEvent.model_validate(row) for row in rows]


def group_by_arrival(
    events: Sequence[ExportedEvent], *, default_received_at: datetime
) -> list[tuple[datetime, list[ExportedEvent]]]:
    """Group exported events by their original ingest time, oldest first.

    A backfill is a replay of the deliveries that originally happened, so it is loaded
    as the batches it originally arrived in rather than as one undifferentiated dump.
    Events with no recorded ingest time are treated as arriving now.

    Args:
        events: Parsed export rows.
        default_received_at: Ingest time for rows that do not carry one.

    Returns:
        ``(received_at, events)`` pairs in ascending ingest-time order.
    """
    batches: dict[datetime, list[ExportedEvent]] = {}
    for event in events:
        batches.setdefault(event.received_at or default_received_at, []).append(event)
    return sorted(batches.items())
