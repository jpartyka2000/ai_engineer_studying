"""The operational store: connection, collection and indexes.

Mongo holds the **raw event stream**. It is written to constantly, read back by id and
by recent time window, and never scanned in full by a request handler -- full scans are
the warehouse's job and the warehouse is DuckDB. Keeping that division explicit is why
this module exposes a narrow set of accessors instead of handing callers a database
object to do as they please with.

**Indexes are created from code, not by hand.** ``ensure_indexes`` is idempotent and is
called by the CLI, by CI and by the API's start-up, because an index that exists only
because somebody once ran a command in a shell is an index that will be missing in the
next environment. The three indexes and their justifications are in
:data:`INDEX_SPECS`.
"""

from __future__ import annotations

import logging
from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from eventstore.config import SETTINGS, Settings

logger = logging.getLogger(__name__)

#: Collection holding the raw event stream.
EVENTS_COLLECTION = "events"

#: Every index this service relies on, with the query each one serves. A compound index
#: is only useful to a query whose equality fields are a prefix of it, so the order of
#: the keys here is a statement about the queries in ``queries.py`` and the two must be
#: changed together.
INDEX_SPECS: list[dict[str, Any]] = [
    {
        "name": "event_id_unique",
        "keys": [("event_id", ASCENDING)],
        "unique": True,
        # Deduplication is enforced by the database, not by a read-then-write in the
        # application. A check-then-insert is a race by construction: two workers
        # replaying the same batch both see "absent" and both insert.
        "why": "retried batches must not double-count",
    },
    {
        "name": "service_occurred_at",
        "keys": [("service", ASCENDING), ("occurred_at", DESCENDING)],
        "unique": False,
        # Equality on service, then a descending range on occurred_at: exactly the
        # shape of recent_events(). Descending so the sort is satisfied by a walk of
        # the index rather than an in-memory sort of the matched set.
        "why": "serves the recent-window query and its sort",
    },
    {
        "name": "received_at",
        "keys": [("received_at", ASCENDING)],
        "unique": False,
        # The rollup advances through ingest time, so this index is what keeps each
        # incremental run proportional to what arrived rather than to the collection.
        "why": "serves the incremental rollup scan",
    },
]


def get_client(settings: Settings | None = None) -> MongoClient:
    """Open a Mongo client.

    Args:
        settings: Override settings, for tests.

    Returns:
        A connected :class:`~pymongo.MongoClient`. The caller closes it, or lets the
        process exit; pymongo pools connections internally, so creating one client per
        process is the intended usage.
    """
    resolved = settings or SETTINGS
    return MongoClient(resolved.mongo_url, tz_aware=True, serverSelectionTimeoutMS=5000)


def get_database(client: MongoClient, settings: Settings | None = None) -> Database:
    """Return the service's database on an open client."""
    resolved = settings or SETTINGS
    return client[resolved.mongo_database]


def get_events(database: Database) -> Collection:
    """Return the events collection."""
    return database[EVENTS_COLLECTION]


def ensure_indexes(collection: Collection) -> list[str]:
    """Create every index in :data:`INDEX_SPECS` if it does not already exist.

    Idempotent: ``create_index`` with an explicit name is a no-op when an identical
    index is already present.

    Args:
        collection: The events collection.

    Returns:
        The index names, in declaration order.
    """
    created: list[str] = []
    for spec in INDEX_SPECS:
        name = collection.create_index(spec["keys"], name=spec["name"], unique=spec["unique"])
        logger.debug("ensured index %s (%s)", name, spec["why"])
        created.append(name)
    return created


def ping(client: MongoClient) -> bool:
    """Return whether the server answers an ``admin.ping``.

    Used by ``/readyz``. Swallows the exception on purpose: a readiness probe reports
    "not ready", it does not raise into the ASGI stack.
    """
    try:
        client.admin.command("ping")
    except Exception:  # noqa: BLE001 - a readiness probe must not propagate
        logger.warning("mongo ping failed", exc_info=True)
        return False
    return True
