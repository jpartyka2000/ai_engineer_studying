"""The HTTP surface.

Two kinds of endpoint, kept apart on purpose because they have different costs and
different stores behind them.

``/v1/events/*``
    **Operational.** Backed by Mongo, bounded by a recent time window, served from an
    index. These are the endpoints an on-call engineer hits while something is on fire,
    so they must stay fast while the collection grows.

``/v1/stats/*``
    **Analytical.** Backed by the DuckDB rollups, which the rollup job maintains. A
    statistics endpoint never touches Mongo: scanning the raw stream to draw a chart is
    how an analytical query takes the operational store down with it.

Handlers here do **no arithmetic**. They parse a window, call
:mod:`eventstore.analytics`, and serialise. Every statistic is somewhere that can be
tested without an HTTP client or a database.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any, AsyncIterator, Iterator

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pymongo.collection import Collection

from eventstore import analytics, duck, mongo, queries
from eventstore.config import SETTINGS, Settings
from eventstore.ingest import ingest_events, utcnow
from eventstore.models import EventOut, IngestRequest, IngestResult
from eventstore.rollup import run_rollup

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the Mongo client once per process and ensure the indexes exist.

    Index creation on start-up is idempotent and takes milliseconds when the indexes
    are already there. It is here rather than in a migration script because an index
    this service's queries depend on must not be able to be missing in an environment
    somebody forgot to run the script in.
    """
    settings: Settings = app.state.settings
    client = mongo.get_client(settings)
    database = mongo.get_database(client, settings)
    collection = mongo.get_events(database)
    try:
        mongo.ensure_indexes(collection)
    except Exception:  # noqa: BLE001 - start-up must not die on a transient Mongo blip
        logger.warning("could not ensure indexes at start-up", exc_info=True)
    app.state.mongo_client = client
    app.state.events = collection
    try:
        yield
    finally:
        client.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI application.

    A factory rather than a module-level singleton so that a test can build an app
    pointed at its own Mongo database and its own warehouse file.

    Args:
        settings: Override settings.

    Returns:
        The configured :class:`~fastapi.FastAPI` app.
    """
    app = FastAPI(
        title="eventstore",
        version="0.4.0",
        summary="Request-event ingestion and the performance model built on it",
        lifespan=lifespan,
    )
    app.state.settings = settings or SETTINGS
    _register_routes(app)
    return app


def events_collection(request: Request) -> Collection:
    """Dependency: the events collection opened by :func:`lifespan`.

    Reached through ``request.app`` rather than a closure so that the annotation
    aliases below can live at module scope -- FastAPI resolves the string annotations
    this module uses against module globals, and a dependency alias defined inside a
    function is invisible to it.
    """
    return request.app.state.events


def warehouse_connection(request: Request) -> Iterator[Any]:
    """Dependency: a warehouse connection, closed when the request ends.

    One connection per request rather than one per process, because DuckDB takes an
    exclusive lock on the database file and a connection held open by the API would
    stop the rollup job from running at all.
    """
    connection = duck.connect(request.app.state.settings)
    try:
        yield connection
    finally:
        connection.close()


EventsDep = Annotated[Collection, Depends(events_collection)]
WarehouseDep = Annotated[Any, Depends(warehouse_connection)]


def _register_routes(app: FastAPI) -> None:
    """Attach every route to ``app``."""

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """Liveness: the process is up. Deliberately touches nothing else."""
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, Any]:
        """Readiness: both stores answer.

        Returns 503 when either is unavailable, because a process that cannot reach
        Mongo will accept an ingest batch and lose it.
        """
        mongo_ok = mongo.ping(app.state.mongo_client)
        try:
            with duck.warehouse(app.state.settings) as connection:
                connection.execute("SELECT 1").fetchone()
            warehouse_ok = True
        except Exception:  # noqa: BLE001 - a probe reports, it does not raise
            logger.warning("warehouse probe failed", exc_info=True)
            warehouse_ok = False

        body = {"mongo": mongo_ok, "warehouse": warehouse_ok}
        if not (mongo_ok and warehouse_ok):
            raise HTTPException(status_code=503, detail=body)
        return {"status": "ready", **body}

    @app.post("/v1/events", status_code=202, response_model=IngestResult)
    def post_events(payload: IngestRequest, collection: EventsDep) -> IngestResult:
        """Accept a batch of events.

        202 rather than 201: the events are durable in the operational store, but they
        are not in the rollups until the rollup job runs, so the request has been
        accepted rather than fully processed.
        """
        return ingest_events(collection, payload.events, received_at=utcnow())

    @app.get("/v1/events/recent", response_model=list[EventOut])
    def get_recent(
        collection: EventsDep,
        service: Annotated[str, Query(min_length=1)],
        minutes: Annotated[int, Query(ge=1, le=1440)] = 15,
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    ) -> list[EventOut]:
        """Most recent events for a service, newest first."""
        return queries.recent_events(collection, service, minutes=minutes, limit=limit)

    @app.get("/v1/stats/latency")
    def get_latency(
        connection: WarehouseDep,
        service: Annotated[str, Query(min_length=1)],
        start: datetime,
        end: datetime,
        route: str | None = None,
    ) -> dict[str, Any]:
        """Percentiles, Apdex and a median interval for a window."""
        try:
            profile = analytics.latency_profile(
                connection,
                service=service,
                route=route,
                start=start,
                end=end,
                seed=app.state.settings.bootstrap_seed,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return profile.as_dict()

    @app.get("/v1/stats/errors")
    def get_errors(
        connection: WarehouseDep,
        service: Annotated[str, Query(min_length=1)],
        start: datetime,
        end: datetime,
    ) -> dict[str, Any]:
        """Error rate for a window, with its Wilson interval."""
        return analytics.error_rate(
            connection, service=service, start=start, end=end
        ).as_dict()

    @app.get("/v1/stats/compare")
    def get_compare(
        connection: WarehouseDep,
        service: Annotated[str, Query(min_length=1)],
        candidate_start: datetime,
        candidate_end: datetime,
        baseline_start: datetime,
        baseline_end: datetime,
        route: str | None = None,
    ) -> dict[str, Any]:
        """Compare two windows' latency distributions."""
        candidate = analytics.latencies_in_window(
            connection, service=service, route=route,
            start=candidate_start, end=candidate_end,
        )
        baseline = analytics.latencies_in_window(
            connection, service=service, route=route,
            start=baseline_start, end=baseline_end,
        )
        try:
            result = analytics.compare_windows(
                candidate, baseline, seed=app.state.settings.bootstrap_seed
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return result.as_dict()

    @app.get("/v1/stats/anomalies")
    def get_anomalies(
        connection: WarehouseDep,
        service: Annotated[str, Query(min_length=1)],
        start: datetime,
        end: datetime,
    ) -> dict[str, Any]:
        """Score each minute of a window against its seasonal baseline."""
        try:
            scores = analytics.anomaly_scan(
                connection, service=service, start=start, end=end
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"service": service, "scores": [score.as_dict() for score in scores]}

    @app.post("/v1/rollup")
    def post_rollup(collection: EventsDep, connection: WarehouseDep) -> dict[str, Any]:
        """Run one incremental rollup. Exposed so CI and the smoke test can drive it."""
        return run_rollup(connection, collection).as_dict()


#: The ASGI application uvicorn serves.
app = create_app()
