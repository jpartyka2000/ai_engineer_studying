"""Incremental load state.

A watermark records how far through *event time* a stream has been processed. It exists so
a daily run reads the new tail of a stream rather than all of history, and the whole value
of it depends on one property:

**A watermark must never move backwards, and must never advance on a failed run.**

Both failures look identical in production -- a day with suspiciously little data -- and
both are silent. If a watermark regresses, the next run re-reads a window that was already
processed. If it advances past work that did not finish, that window is skipped forever and
nothing ever notices, because the pipeline is, from then on, consistently looking past it.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

import duckdb

#: Returned for a stream that has never run. Chosen rather than NULL so callers can compare
#: without a special case; it is before any plausible event.
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class WatermarkRegression(RuntimeError):
    """Raised when something tries to move a watermark backwards."""


def get_watermark(connection: duckdb.DuckDBPyConnection, stream: str) -> datetime:
    """Return a stream's watermark, or :data:`EPOCH` if it has never run.

    Args:
        connection: An open warehouse connection.
        stream: The stream name.

    Returns:
        An aware UTC :class:`datetime`.
    """
    row = connection.execute(
        "SELECT position FROM watermarks WHERE stream = ?", [stream]
    ).fetchone()
    if row is None:
        return EPOCH
    position = row[0]
    # DuckDB hands back a naive datetime for a TIMESTAMP column. Everything written here
    # was UTC, so attaching the zone back is restoring information rather than assuming it.
    return position.replace(tzinfo=timezone.utc) if position.tzinfo is None else position


def advance_watermark(
    connection: duckdb.DuckDBPyConnection, stream: str, position: datetime
) -> datetime:
    """Move a stream's watermark forward.

    Args:
        connection: An open warehouse connection.
        stream: The stream name.
        position: The new position, which must be at or after the current one.

    Returns:
        The stored position.

    Raises:
        WatermarkRegression: If ``position`` is earlier than the current watermark. Raising
            rather than clamping: a caller computing an earlier position has a bug, and
            silently keeping the old value hides it until someone asks why a backfill
            produced nothing.
        ValueError: If ``position`` is naive. A watermark compared against an instant in
            another zone is worse than no watermark.
    """
    if position.tzinfo is None:
        raise ValueError("a watermark position must be timezone-aware")
    position = position.astimezone(timezone.utc)

    current = get_watermark(connection, stream)
    if position < current:
        raise WatermarkRegression(
            f"stream {stream!r}: refusing to move the watermark from {current.isoformat()} "
            f"back to {position.isoformat()}"
        )

    connection.execute(
        "INSERT INTO watermarks (stream, position, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT (stream) DO UPDATE SET position = excluded.position, "
        "updated_at = excluded.updated_at",
        [stream, position, datetime.now(timezone.utc)],
    )
    return position


@contextmanager
def watermark_advanced_on_success(
    connection: duckdb.DuckDBPyConnection, stream: str, position: datetime
) -> Iterator[None]:
    """Advance a watermark only if the wrapped work completes.

    The ordering is the whole point. The body runs first; the watermark moves afterwards.
    Advancing first and then working means an exception leaves the watermark past data that
    was never processed, and that window is never looked at again.

    Args:
        connection: An open warehouse connection.
        stream: The stream name.
        position: Where to move the watermark once the body succeeds.

    Yields:
        Nothing. Use it as a plain ``with`` block around the work.
    """
    yield
    advance_watermark(connection, stream, position)


def max_event_time(connection: duckdb.DuckDBPyConnection) -> datetime:
    """Return the latest event instant in silver, or :data:`EPOCH` when it is empty.

    This is the only defensible position for the usage watermark: the newest *event* that
    has actually been processed, not the time the job happened to run. Using wall-clock
    time would skip any event that arrives late, which for usage telemetry is most of them.
    """
    row = connection.execute("SELECT max(occurred_at) FROM silver_usage").fetchone()
    if row is None or row[0] is None:
        return EPOCH
    value = row[0]
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
