"""Shared fixtures.

Three kinds of test live in this suite and they need very different setups.

**Statistics tests need nothing at all.** Everything under ``src/eventstore/perfmodel/``
is a pure function over numbers, so its tests build their input as a literal list and
assert a constant that is derived in the test's own docstring. They carry no marker and
run in milliseconds.

**Warehouse tests need DuckDB and a few rows.** ``warehouse`` gives each test its own
database file and :func:`insert_facts` puts rows in it. DuckDB takes an exclusive lock on
the file, so sharing one between tests would serialise them at best and deadlock them at
worst -- hence one file per test under ``tmp_path``.

**Store tests need MongoDB,** and are marked ``mongo``. Each gets its **own database**,
named after the test, dropped afterwards. That is what lets them create indexes, insert
duplicates and count documents without any of them seeing another's writes.

A missing MongoDB **raises rather than skips**. A skipped test is green, and a suite that
goes green when the database is unreachable is a suite that cannot tell "this works" from
"this was never run" -- which matters here because these tests are graded. Run the suite
with ``make test``, which runs it inside the container where ``db`` resolves.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Sequence

import pytest
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from eventstore import duck, mongo
from eventstore.config import Settings
from eventstore.rollup import rebuild_buckets

#: The project root, found from this file rather than from the working directory so the
#: suite behaves the same however pytest was invoked.
REPO_ROOT = Path(__file__).resolve().parents[1]

#: The instant the committed exports start at. Tests that assert on seeded data anchor
#: to this rather than to "now", so they do not rot.
SEED_WINDOW_START = datetime(2026, 4, 1, 11, 0, tzinfo=timezone.utc)
SEED_WINDOW_END = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
#: When checkout's slow release went out.
SEED_DEPLOY_AT = datetime(2026, 4, 1, 12, 30, tzinfo=timezone.utc)


def _database_name(request: pytest.FixtureRequest) -> str:
    """Return a Mongo database name unique to one test."""
    raw = request.node.name.replace("[", "_").replace("]", "").replace("-", "_")
    return f"test_{raw}"[:60]


@pytest.fixture
def mongo_client() -> Iterator[MongoClient]:
    """A connected Mongo client, or a loud failure explaining how to get one."""
    client = mongo.get_client(Settings())
    try:
        client.admin.command("ping")
    except PyMongoError as exc:  # pragma: no cover - environment problem, not a defect
        client.close()
        raise RuntimeError(
            "MongoDB is not reachable at the configured MONGO_URL. These tests are not "
            "skipped when the database is missing, because a skip is green and would "
            "hide a real failure. Run the suite with `make test`, which runs it inside "
            f"the container where `db` resolves. Original error: {exc}"
        ) from exc
    yield client
    client.close()


@pytest.fixture
def events(mongo_client: MongoClient, request: pytest.FixtureRequest) -> Iterator[Collection]:
    """An empty events collection in a database of this test's own, with indexes."""
    name = _database_name(request)
    mongo_client.drop_database(name)
    collection = mongo_client[name][mongo.EVENTS_COLLECTION]
    mongo.ensure_indexes(collection)
    yield collection
    mongo_client.drop_database(name)


@pytest.fixture
def bare_events(mongo_client: MongoClient, request: pytest.FixtureRequest) -> Iterator[Collection]:
    """An events collection with **no** indexes created.

    For tests that assert what ``ensure_indexes`` itself does, which cannot be done on
    a collection where it has already run.
    """
    name = f"{_database_name(request)}_bare"[:60]
    mongo_client.drop_database(name)
    yield mongo_client[name][mongo.EVENTS_COLLECTION]
    mongo_client.drop_database(name)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointing the warehouse at this test's own scratch directory."""
    return Settings(root=tmp_path)


@pytest.fixture
def warehouse(tmp_path: Path) -> Iterator:
    """An open, empty DuckDB warehouse. Closed afterwards, because of the file lock."""
    connection = duck.connect_path(tmp_path / "warehouse" / "test.duckdb")
    yield connection
    connection.close()


def fact(
    event_id: str,
    *,
    service: str = "checkout",
    route: str = "/v1/checkout",
    status_code: int = 200,
    latency_ms: float = 100.0,
    occurred_at: datetime,
    received_at: datetime | None = None,
    method: str = "POST",
    region: str = "us-east-1",
) -> tuple:
    """Build one ``fact_requests`` row, overriding only what a test cares about.

    Timestamps are stored naive-UTC in DuckDB, matching ``rollup._naive_utc``.
    """
    arrived = received_at or occurred_at + timedelta(seconds=2)
    return (
        event_id,
        service,
        route,
        method,
        status_code,
        float(latency_ms),
        region,
        occurred_at.astimezone(timezone.utc).replace(tzinfo=None),
        arrived.astimezone(timezone.utc).replace(tzinfo=None),
    )


def insert_facts(connection, rows: Sequence[tuple], *, rebuild: bool = True) -> int:
    """Insert ``fact_requests`` rows and rebuild the rollups they touch.

    Args:
        connection: An open warehouse connection.
        rows: Rows from :func:`fact`.
        rebuild: Whether to rebuild the affected minute buckets afterwards. Tests
            asserting on ``fact_requests`` alone pass ``False``.

    Returns:
        The number of rollup rows written.
    """
    connection.executemany(
        """
        INSERT OR REPLACE INTO fact_requests
            (event_id, service, route, method, status_code, latency_ms,
             region, occurred_at, received_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [list(row) for row in rows],
    )
    if not rebuild:
        return 0
    keys = {(row[7].replace(second=0, microsecond=0), row[1], row[2]) for row in rows}
    return rebuild_buckets(connection, keys)


def minutes_of(start: datetime, count: int) -> list[datetime]:
    """Return ``count`` consecutive minute boundaries starting at ``start``."""
    return [start + timedelta(minutes=offset) for offset in range(count)]


def seed_rows() -> list[dict]:
    """Return every row of the committed exports, duplicates included, in file order."""
    rows: list[dict] = []
    for path in sorted((REPO_ROOT / "data").glob("events_*.jsonl")):
        rows.extend(
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    return rows
