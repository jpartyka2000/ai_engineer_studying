"""The operational read path.

Every query in this module is **bounded**: by a time range, by a limit, or by both. An
operational store is queried from request handlers, and a handler whose cost grows with
the age of the service is a handler that works in week one and pages somebody in month
four.

Each function names the index it expects to use. :func:`explain_recent` exists so that
expectation is testable rather than aspirational -- it reports how many documents the
server examined to return how many, and a ratio far from 1 means an index is missing or
the query stopped matching the one it was written for.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from pymongo.collection import Collection

from eventstore.config import MAX_RECENT_MINUTES
from eventstore.ingest import utcnow
from eventstore.models import ERROR_STATUS_FLOOR, EventOut

#: Fields returned by the recent-window query. Projected rather than fetched whole: the
#: endpoint renders seven fields and the documents are not large, but the projection is
#: what lets the server answer from the index when the query allows it.
RECENT_PROJECTION: dict[str, int] = {
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


def recent_window(minutes: int, now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return the ``[start, end)`` range for a recent-minutes query.

    Args:
        minutes: Window length, clamped to :data:`~eventstore.config.MAX_RECENT_MINUTES`.
        now: End of the window. Defaults to the current instant.

    Returns:
        A half-open range of timezone-aware UTC datetimes.

    Raises:
        ValueError: If ``minutes`` is not positive.
    """
    if minutes <= 0:
        raise ValueError(f"minutes must be > 0, got {minutes!r}")
    end = now or utcnow()
    return end - timedelta(minutes=min(minutes, MAX_RECENT_MINUTES)), end


def recent_cursor(
    collection: Collection,
    service: str,
    *,
    minutes: int = 15,
    limit: int = 100,
    now: datetime | None = None,
):
    """Build the cursor behind ``/v1/events/recent``.

    **One definition, two callers.** :func:`recent_events` iterates this cursor and
    :func:`explain_recent` explains it, so the plan that gets measured is by
    construction the plan that gets run. Writing the query twice -- once for the
    endpoint and once for the benchmark -- is how a measurement stays green while the
    endpoint it claims to cover regresses.

    The shape is chosen to match the ``service_occurred_at`` index: equality on
    ``service`` is the index prefix, the descending sort on ``occurred_at`` is the
    index order, and ``limit`` is applied by the server. The server therefore walks
    the index and stops, examining about as many documents as it returns.

    Args:
        collection: The events collection.
        service: Exact service name.
        minutes: How far back to look.
        limit: Maximum events to return. Applied by the *server*: a limit applied
            after the documents have been fetched is not a limit, it is a slice of
            everything.
        now: End of the window, for tests.

    Returns:
        An unevaluated :class:`~pymongo.cursor.Cursor`.
    """
    start, end = recent_window(minutes, now)
    return (
        collection.find(
            {"service": service, "occurred_at": {"$gte": start, "$lt": end}},
            RECENT_PROJECTION,
        )
        .sort("occurred_at", -1)
        .limit(limit)
    )


def recent_events(
    collection: Collection,
    service: str,
    *,
    minutes: int = 15,
    limit: int = 100,
    now: datetime | None = None,
) -> list[EventOut]:
    """Return a service's most recent events, newest first.

    Args:
        collection: The events collection.
        service: Exact service name.
        minutes: How far back to look.
        limit: Maximum events to return.
        now: End of the window, for tests.

    Returns:
        Events, newest first.
    """
    cursor = recent_cursor(collection, service, minutes=minutes, limit=limit, now=now)
    return [EventOut.from_document(document) for document in cursor]


def latency_sample(
    collection: Collection,
    *,
    service: str,
    route: str | None = None,
    start: datetime,
    end: datetime,
) -> list[float]:
    """Return the latencies of a service's events in a window.

    Args:
        collection: The events collection.
        service: Exact service name.
        route: Optional exact route; ``None`` pools every route.
        start: Window start, inclusive.
        end: Window end, exclusive.

    Returns:
        Latencies in milliseconds, in no particular order. The caller sorts, because
        every consumer in ``perfmodel`` sorts anyway.
    """
    criteria: dict[str, Any] = {"service": service, "occurred_at": {"$gte": start, "$lt": end}}
    if route is not None:
        criteria["route"] = route
    return [
        float(document["latency_ms"])
        for document in collection.find(criteria, {"_id": 0, "latency_ms": 1})
    ]


def error_counts(
    collection: Collection,
    *,
    service: str,
    start: datetime,
    end: datetime,
) -> tuple[int, int]:
    """Return ``(errors, total)`` for a service in a window.

    Counted in one aggregation rather than two ``count_documents`` calls, so the two
    numbers describe the same set of documents even while the collection is being
    written to.

    Args:
        collection: The events collection.
        service: Exact service name.
        start: Window start, inclusive.
        end: Window end, exclusive.

    Returns:
        ``(errors, total)``. ``(0, 0)`` for an empty window -- which the caller must
        distinguish from a measured zero error rate, and which is exactly why the
        error endpoint reports a Wilson interval rather than a bare proportion.
    """
    pipeline = [
        {"$match": {"service": service, "occurred_at": {"$gte": start, "$lt": end}}},
        {
            "$group": {
                "_id": None,
                "total": {"$sum": 1},
                "errors": {
                    "$sum": {"$cond": [{"$gte": ["$status_code", ERROR_STATUS_FLOOR]}, 1, 0]}
                },
            }
        },
    ]
    rows = list(collection.aggregate(pipeline))
    if not rows:
        return 0, 0
    return int(rows[0]["errors"]), int(rows[0]["total"])


def explain_recent(
    collection: Collection,
    service: str,
    *,
    minutes: int = 15,
    limit: int = 100,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Explain the recent-window query and report what the server did.

    Explains :func:`recent_cursor` -- the same cursor the endpoint iterates -- so this
    cannot report on a query the service does not actually run.

    Args:
        collection: The events collection.
        service: Exact service name.
        minutes: Window length.
        limit: Query limit.
        now: End of the window, for tests.

    Returns:
        A dict with ``docs_examined``, ``keys_examined``, ``docs_returned``,
        ``stage`` (the winning plan's root stage), ``index_name`` (``None`` for a
        collection scan) and ``sort_in_memory``. ``docs_examined`` is the number a
        benchmark asserts on: unlike a wall-clock time it does not depend on how busy
        the machine is.
    """
    explained = recent_cursor(
        collection, service, minutes=minutes, limit=limit, now=now
    ).explain()

    execution = explained.get("executionStats", {})
    plan = execution.get("executionStages", {})
    winning = explained.get("queryPlanner", {}).get("winningPlan", {})
    return {
        "docs_examined": int(execution.get("totalDocsExamined", -1)),
        "keys_examined": int(execution.get("totalKeysExamined", -1)),
        "docs_returned": int(execution.get("nReturned", -1)),
        "stage": plan.get("stage", "UNKNOWN"),
        "index_name": _winning_index(winning),
        # A SORT stage means the server could not get the order from an index and had
        # to materialise and sort the whole matched set before applying the limit.
        # That is the difference between reading a hundred documents and reading
        # every document in the window, and no index name on its own will show it.
        "sort_in_memory": int(_has_stage(winning, "SORT") or _has_stage(plan, "SORT")),
    }


def _has_stage(plan: dict[str, Any], stage: str) -> bool:
    """Return whether ``stage`` appears anywhere in an execution plan tree."""
    if plan.get("stage") == stage:
        return True
    for key in ("inputStage", "queryPlan"):
        if key in plan and _has_stage(plan[key], stage):
            return True
    return any(_has_stage(child, stage) for child in plan.get("inputStages", []))


def _winning_index(plan: dict[str, Any]) -> str | None:
    """Walk a winning plan and return the index name it uses, if any."""
    if "indexName" in plan:
        return str(plan["indexName"])
    for key in ("inputStage", "queryPlan"):
        if key in plan:
            return _winning_index(plan[key])
    for child in plan.get("inputStages", []):
        found = _winning_index(child)
        if found is not None:
            return found
    return None
