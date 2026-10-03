"""The HTTP surface.

One endpoint does the interesting thing and the rest exist to make it operable.

Handlers here **resolve a tenant, open a transaction, and call the pipeline.** They do
not build SQL, decide what is safe, or interpret results. That is why the error mapping
is the most opinionated thing in the file: a refusal is a 400 because the request will
never work, a failure is a 500 because it might work next time, and collapsing the two
would make a probing attacker indistinguishable from a flaky database.

**The tenant comes from the API key and from nowhere else.** There is no tenant
parameter on any endpoint, no header a client can set, and no override for internal
callers. Every one of those is a feature somebody eventually asks for and every one of
them is the bug this service exists not to have.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from sqlgenie.config import MODEL, SETTINGS, Settings
from sqlgenie.db import pool
from sqlgenie.llm.recorded_client import RecordedClient
from sqlgenie.nl2sql import audit, catalog, pipeline
from sqlgenie.nl2sql.executor import ExecutionError
from sqlgenie.nl2sql.pipeline import RefusedError
from sqlgenie.tenancy import context
from sqlgenie.tenancy.auth import AuthenticationError, resolve_tenant

logger = logging.getLogger(__name__)


class AskRequest(BaseModel):
    """A question to answer."""

    model_config = {"extra": "forbid"}

    question: str = Field(min_length=1, max_length=500)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI application.

    A factory rather than a module-level singleton so a test can point an app at its own
    database and cassette directory.
    """
    app = FastAPI(
        title="sqlgenie",
        version="0.6.0",
        summary="Ask a question in English, get an answer from your own data only",
    )
    app.state.settings = settings or SETTINGS
    app.state.client = RecordedClient(app.state.settings.cassette_dir, model=MODEL)
    _register_routes(app)
    return app


def tenant_from_key(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> str:
    """Resolve the tenant for a request, mapping auth failures to 401.

    Settings are reached through ``request.app`` rather than a closure so that the
    annotation alias below can live at module scope. FastAPI resolves this module's
    string annotations against module globals, and a dependency alias defined inside a
    function is invisible to it -- the parameter is then treated as a query parameter
    and every request fails validation with a 422.
    """
    try:
        return resolve_tenant(x_api_key, request.app.state.settings)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


TenantDep = Annotated[str, Depends(tenant_from_key)]


def _register_routes(app: FastAPI) -> None:
    """Attach every route to ``app``."""

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """Liveness. Touches nothing."""
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, Any]:
        """Readiness: the database answers and the cassette set is present."""
        try:
            with pool.app_connection(app.state.settings) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
            database_ok = True
        except Exception:  # noqa: BLE001 - a probe reports, it does not raise
            logger.warning("database probe failed", exc_info=True)
            database_ok = False

        cassettes = len(app.state.client.keys())
        body = {"database": database_ok, "cassettes": cassettes}
        if not database_ok or cassettes == 0:
            raise HTTPException(status_code=503, detail=body)
        return {"status": "ready", **body}

    @app.get("/v1/schema")
    def get_schema(tenant_id: TenantDep) -> dict[str, Any]:
        """The queryable schema.

        Table and column names only. No row counts, no sample values, no min/max -- all
        of which are things somebody will ask for to "help the model", and all of which
        would make this endpoint a way to read another tenant's data one statistic at a
        time.
        """
        return {
            "tables": [
                {
                    "name": spec.name,
                    "columns": list(spec.columns),
                    "tenant_scoped": spec.tenant_scoped,
                    "description": spec.description,
                }
                for _, spec in sorted(catalog.TABLES.items())
            ]
        }

    @app.post("/v1/ask")
    def ask(payload: AskRequest, tenant_id: TenantDep) -> dict[str, Any]:
        """Answer a question against the caller's own data."""
        with context.bind_tenant(tenant_id):
            try:
                with pool.app_connection(app.state.settings) as connection:
                    answer = pipeline.ask(
                        payload.question,
                        connection=connection,
                        client=app.state.client,
                        tenant_id=tenant_id,
                        max_rows=app.state.settings.max_rows,
                        statement_timeout_ms=app.state.settings.statement_timeout_ms,
                    )
            except RefusedError as exc:
                # 400, not 500: the request is understood and will not be served. A
                # 500 here would put an attacker's probing in the same bucket as a
                # database outage, and page somebody for the wrong reason.
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except ExecutionError as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
        return answer.as_dict()

    @app.get("/v1/audit")
    def get_audit(tenant_id: TenantDep, limit: int = 50) -> dict[str, Any]:
        """Recent auditable events for the caller's tenant.

        Scoped to the caller like everything else: the audit trail of a multi-tenant
        service is itself tenant data, and an audit endpoint that returned everything
        would be the most efficient cross-tenant read in the product.
        """
        entries = audit.records(tenant_id=tenant_id)[-limit:]
        return {"records": [entry.as_dict() for entry in entries]}


#: The ASGI application uvicorn serves.
app = create_app()
