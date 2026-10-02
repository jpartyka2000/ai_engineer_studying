"""The analytical store: DuckDB, and the schema the rollups live in.

**Why a second database at all.** Mongo is good at the write path and at point and
recent-range reads; it is not where you want to scan a month of events to produce a
dashboard. DuckDB is columnar, in-process and reads a month of minute buckets in
milliseconds, and because it is a library there is no second server to operate. The
split is the ordinary operational/analytical one, made explicit:

=================  ===========================================================
Store              Holds
=================  ===========================================================
Mongo ``events``   The raw stream. Append-only, queried by id and recent window.
DuckDB ``fact_``   A typed copy of the events the rollup has consumed.
DuckDB ``rollup_`` Derived aggregates. Rebuildable from ``fact_requests`` alone.
=================  ===========================================================

Everything in DuckDB is **derived state**: delete the file and ``eventstore rollup
--full`` rebuilds it from Mongo. That is why the warehouse is gitignored and why no
endpoint writes to it outside the rollup.

The schema is applied on every connect and is written to be safe to re-apply, because a
rollup job is restarted far more often than it is first run.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import duckdb

from eventstore.config import SETTINGS, Settings

#: Name of the rollup's incremental-progress row in ``rollup_state``.
ROLLUP_STREAM = "events"

#: Applied on every connect. Idempotent by construction.
SCHEMA = """
-- A typed copy of every event the rollup has consumed. Keyed by event_id, so a
-- replayed batch updates in place instead of double-counting -- the same guarantee the
-- unique index gives on the Mongo side, restated where the aggregates are computed.
CREATE TABLE IF NOT EXISTS fact_requests (
    event_id     VARCHAR NOT NULL PRIMARY KEY,
    service      VARCHAR NOT NULL,
    route        VARCHAR NOT NULL,
    method       VARCHAR NOT NULL,
    status_code  INTEGER NOT NULL,
    latency_ms   DOUBLE  NOT NULL,
    region       VARCHAR NOT NULL,
    occurred_at  TIMESTAMP NOT NULL,   -- event time, UTC
    received_at  TIMESTAMP NOT NULL    -- ingest time, UTC
);

-- One row per (minute, service, route). Percentiles are stored rather than recomputed
-- because the raw latencies behind a bucket are what make a month of history large,
-- and because a stored p95 is the number the SLO report cited at the time.
CREATE TABLE IF NOT EXISTS rollup_minute (
    bucket        TIMESTAMP NOT NULL,
    service       VARCHAR NOT NULL,
    route         VARCHAR NOT NULL,
    requests      BIGINT NOT NULL,
    errors        BIGINT NOT NULL,
    sum_latency_ms DOUBLE NOT NULL,
    p50_ms        DOUBLE NOT NULL,
    p95_ms        DOUBLE NOT NULL,
    p99_ms        DOUBLE NOT NULL,
    max_latency_ms DOUBLE NOT NULL,
    PRIMARY KEY (bucket, service, route)
);

-- Incremental progress, one row per stream. The position is an *ingest* time, not an
-- event time: the rollup's job is to consume everything that has arrived, and events
-- arrive out of order. See rollup.py for what goes wrong if this is confused.
CREATE TABLE IF NOT EXISTS rollup_state (
    stream     VARCHAR NOT NULL PRIMARY KEY,
    position   TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
"""


def connect(
    settings: Settings | None = None, *, read_only: bool = False
) -> duckdb.DuckDBPyConnection:
    """Open the warehouse, applying the schema.

    Args:
        settings: Override settings, for tests.
        read_only: Open without write ability. The schema is not applied in this mode
            because applying it would be a write.

    Returns:
        An open connection. The caller closes it, or uses :func:`warehouse`.
    """
    resolved = (settings or SETTINGS).ensure_dirs()
    connection = duckdb.connect(str(resolved.warehouse_path), read_only=read_only)
    if not read_only:
        connection.execute(SCHEMA)
    return connection


@contextmanager
def warehouse(
    settings: Settings | None = None, *, read_only: bool = False
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Context manager around :func:`connect`.

    DuckDB takes an exclusive lock on the database file, so a leaked connection makes
    every later run fail with a lock error that points at the wrong place entirely.
    """
    connection = connect(settings, read_only=read_only)
    try:
        yield connection
    finally:
        connection.close()


def connect_path(path: str | Path) -> duckdb.DuckDBPyConnection:
    """Open a warehouse at an explicit path, applying the schema.

    Used by tests and by the benchmark, which both want a throwaway file rather than
    the service's own.
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(path))
    connection.execute(SCHEMA)
    return connection


def table_count(connection: duckdb.DuckDBPyConnection, table: str) -> int:
    """Return the row count of a table.

    Args:
        connection: An open connection.
        table: Table name. Interpolated, so it must not come from user input; every
            call site in this package passes a literal.

    Returns:
        The number of rows.
    """
    return int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])  # noqa: S608
