"""The pipeline: Mongo event stream -> DuckDB facts -> minute rollups.

Three properties this job is built around, each of which is a way ETL pipelines usually
go wrong.

**The watermark is ingest time, and the load is idempotent.** The rollup consumes
everything that has *arrived* since it last ran, so the watermark tracks ``received_at``.
Tracking ``occurred_at`` instead looks equivalent and is not: events arrive late, and a
watermark that has advanced past a late event's *event* time will never select it. The
totals for the current window stay perfectly plausible while older buckets quietly stop
being correct -- which is the worst kind of data bug, because nothing is ever red.

**The watermark is inclusive (``$gte``) rather than exclusive.** A whole ingest batch
shares one ``received_at``, so an exclusive watermark combined with a batch limit can cut
a tie group in half and skip its remainder forever. Inclusive re-reads the boundary group
on every run, which is harmless because ``INSERT OR REPLACE`` on ``event_id`` makes the
load idempotent. At-least-once with an idempotent sink beats exactly-once with a subtle
hole in it.

**Rollups are rebuilt per affected bucket, not appended to.** A late event belongs to an
old minute, and that minute's aggregate has already been written. Recomputing every
bucket a load touched -- rather than incrementing counters -- is what lets a late arrival
correct history instead of being added to whatever bucket is current.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence

import duckdb
from pymongo.collection import Collection

from eventstore.duck import ROLLUP_STREAM
from eventstore.ingest import utcnow
from eventstore.models import ERROR_STATUS_FLOOR
from eventstore.perfmodel.percentiles import summarize

logger = logging.getLogger(__name__)

#: Start of time for a stream that has never run.
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

#: Events arriving more than this long after they happened are counted as late and
#: reported. Not an error -- a buffering gateway is behaving correctly -- but a number
#: that should be looked at when it moves.
LATE_ARRIVAL_THRESHOLD = timedelta(seconds=120)

#: Maximum events consumed by one incremental run. Bounds memory and makes a backfill
#: resumable; the CLI loops until a run reports nothing new.
DEFAULT_BATCH_LIMIT = 50_000

#: Fields the rollup reads. Projected because the rollup is the one query in this
#: service that legitimately scans a lot of documents.
ROLLUP_PROJECTION = {
    "_id": 0,
    "event_id": 1,
    "service": 1,
    "route": 1,
    "method": 1,
    "status_code": 1,
    "latency_ms": 1,
    "region": 1,
    "occurred_at": 1,
    "received_at": 1,
}


@dataclass
class RollupReport:
    """What one rollup run did.

    Attributes:
        events_loaded: Documents written into ``fact_requests``, including
            re-written boundary duplicates.
        late_events: Of those, how many arrived more than
            :data:`LATE_ARRIVAL_THRESHOLD` after they happened.
        buckets_rebuilt: ``(bucket, service, route)`` rows recomputed.
        watermark: The ingest-time position after the run.
        oldest_event_loaded: Earliest ``occurred_at`` in the loaded set, or ``None``.
            A value far behind the watermark means history was corrected.
    """

    events_loaded: int = 0
    late_events: int = 0
    buckets_rebuilt: int = 0
    watermark: datetime = EPOCH
    oldest_event_loaded: datetime | None = None
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        """Return the report as a JSON-serialisable dict."""
        return {
            "events_loaded": self.events_loaded,
            "late_events": self.late_events,
            "buckets_rebuilt": self.buckets_rebuilt,
            "watermark": self.watermark.isoformat(),
            "oldest_event_loaded": (
                self.oldest_event_loaded.isoformat() if self.oldest_event_loaded else None
            ),
            "errors": self.errors,
        }


def _naive_utc(moment: datetime) -> datetime:
    """Return ``moment`` as a naive UTC datetime.

    DuckDB's ``TIMESTAMP`` carries no zone. Every timestamp crossing this boundary is
    converted in exactly these two functions so that the convention -- stored naive,
    always UTC -- is stated once and cannot drift.
    """
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


def _aware_utc(moment: datetime) -> datetime:
    """Return a naive warehouse timestamp as timezone-aware UTC."""
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment


def get_position(connection: duckdb.DuckDBPyConnection) -> datetime:
    """Return the rollup's ingest-time watermark, or :data:`EPOCH` if it has never run."""
    row = connection.execute(
        "SELECT position FROM rollup_state WHERE stream = ?", [ROLLUP_STREAM]
    ).fetchone()
    return EPOCH if row is None else _aware_utc(row[0])


def set_position(connection: duckdb.DuckDBPyConnection, position: datetime) -> None:
    """Write the rollup's watermark.

    Args:
        connection: An open warehouse connection.
        position: The new ingest-time position, timezone-aware.
    """
    connection.execute(
        """
        INSERT OR REPLACE INTO rollup_state (stream, position, updated_at)
        VALUES (?, ?, ?)
        """,
        [ROLLUP_STREAM, _naive_utc(position), _naive_utc(utcnow())],
    )


def load_new_events(
    connection: duckdb.DuckDBPyConnection,
    collection: Collection,
    *,
    batch_limit: int = DEFAULT_BATCH_LIMIT,
    full: bool = False,
) -> tuple[RollupReport, set[tuple[datetime, str, str]]]:
    """Copy newly arrived events from Mongo into ``fact_requests``.

    Selection is on ``received_at``, inclusive of the watermark. See the module
    docstring for why both of those words matter.

    Args:
        connection: An open warehouse connection.
        collection: The Mongo events collection.
        batch_limit: Maximum documents to consume in this run.
        full: Ignore the watermark and reload from :data:`EPOCH`. Safe at any time,
            because the sink is keyed on ``event_id``.

    Returns:
        A ``(report, dirty_keys)`` pair, where ``dirty_keys`` holds every
        ``(bucket, service, route)`` whose aggregate the load invalidated.
    """
    position = EPOCH if full else get_position(connection)
    cursor = (
        collection.find({"received_at": {"$gte": position}}, ROLLUP_PROJECTION)
        .sort("received_at", 1)
        .limit(batch_limit)
    )

    report = RollupReport(watermark=position)
    dirty: set[tuple[datetime, str, str]] = set()
    rows: list[Sequence[object]] = []

    for document in cursor:
        occurred_at = _aware_utc(document["occurred_at"])
        received_at = _aware_utc(document["received_at"])
        rows.append(
            (
                document["event_id"],
                document["service"],
                document["route"],
                document.get("method", "GET"),
                int(document["status_code"]),
                float(document["latency_ms"]),
                document.get("region", "unknown"),
                _naive_utc(occurred_at),
                _naive_utc(received_at),
            )
        )
        dirty.add((_naive_utc(occurred_at).replace(second=0, microsecond=0),
                   document["service"], document["route"]))
        if received_at - occurred_at > LATE_ARRIVAL_THRESHOLD:
            report.late_events += 1
        if report.oldest_event_loaded is None or occurred_at < report.oldest_event_loaded:
            report.oldest_event_loaded = occurred_at
        if received_at > report.watermark:
            report.watermark = received_at

    if rows:
        connection.executemany(
            """
            INSERT OR REPLACE INTO fact_requests
                (event_id, service, route, method, status_code, latency_ms,
                 region, occurred_at, received_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        report.events_loaded = len(rows)
        set_position(connection, report.watermark)

    logger.info(
        "loaded %d event(s), %d late, watermark now %s",
        report.events_loaded,
        report.late_events,
        report.watermark.isoformat(),
    )
    return report, dirty


def rebuild_buckets(
    connection: duckdb.DuckDBPyConnection,
    keys: Iterable[tuple[datetime, str, str]],
) -> int:
    """Recompute ``rollup_minute`` for the given ``(bucket, service, route)`` keys.

    Percentiles come from :func:`eventstore.perfmodel.percentiles.summarize` rather
    than from DuckDB's ``quantile_disc``. The two use different rank conventions, and
    a system with two definitions of p95 is a system whose dashboard and whose SLO
    report disagree by one observation and nobody can say which is right.

    Args:
        connection: An open warehouse connection.
        keys: Buckets to rebuild. Naive UTC minute boundaries.

    Returns:
        The number of rollup rows written.
    """
    wanted = sorted(set(keys))
    if not wanted:
        return 0

    connection.execute(
        "CREATE OR REPLACE TEMP TABLE dirty_buckets "
        "(bucket TIMESTAMP, service VARCHAR, route VARCHAR)"
    )
    connection.executemany(
        "INSERT INTO dirty_buckets VALUES (?, ?, ?)", [list(key) for key in wanted]
    )

    sample_rows = connection.execute(
        """
        SELECT date_trunc('minute', f.occurred_at) AS bucket,
               f.service,
               f.route,
               f.status_code,
               f.latency_ms
        FROM fact_requests AS f
        JOIN dirty_buckets AS d
          ON d.bucket = date_trunc('minute', f.occurred_at)
         AND d.service = f.service
         AND d.route = f.route
        """
    ).fetchall()

    grouped: dict[tuple[datetime, str, str], list[tuple[int, float]]] = {}
    for bucket, service, route, status_code, latency_ms in sample_rows:
        grouped.setdefault((bucket, service, route), []).append((int(status_code), float(latency_ms)))

    # A key with no surviving facts is a bucket that was emptied; its stale aggregate
    # has to go, or a deleted minute keeps reporting the traffic it used to have.
    empty = [key for key in wanted if key not in grouped]
    if empty:
        connection.executemany(
            "DELETE FROM rollup_minute WHERE bucket = ? AND service = ? AND route = ?",
            [list(key) for key in empty],
        )

    written: list[Sequence[object]] = []
    for (bucket, service, route), samples in grouped.items():
        latencies = [latency for _, latency in samples]
        stats = summarize(latencies)
        written.append(
            (
                bucket,
                service,
                route,
                len(samples),
                sum(1 for status, _ in samples if status >= ERROR_STATUS_FLOOR),
                sum(latencies),
                stats.p50,
                stats.p95,
                stats.p99,
                stats.max,
            )
        )

    if written:
        connection.executemany(
            """
            INSERT OR REPLACE INTO rollup_minute
                (bucket, service, route, requests, errors, sum_latency_ms,
                 p50_ms, p95_ms, p99_ms, max_latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            written,
        )
    return len(written)


def run_rollup(
    connection: duckdb.DuckDBPyConnection,
    collection: Collection,
    *,
    batch_limit: int = DEFAULT_BATCH_LIMIT,
    full: bool = False,
) -> RollupReport:
    """Run one incremental rollup: load, then rebuild every bucket the load touched.

    Args:
        connection: An open warehouse connection.
        collection: The Mongo events collection.
        batch_limit: Maximum documents to consume.
        full: Reload everything from :data:`EPOCH`.

    Returns:
        A :class:`RollupReport`.
    """
    report, dirty = load_new_events(
        connection, collection, batch_limit=batch_limit, full=full
    )
    report.buckets_rebuilt = rebuild_buckets(connection, dirty)
    return report
