"""The HTTP surface.

Thin by design. Handlers resolve a session, call the pipeline, record the turn and
serialise -- they make no retrieval decisions, assemble no prompts and score nothing.

**The index is built once, at start-up.** Chunking and fitting the vectoriser over this
corpus takes milliseconds, but doing it per request would make every answer pay for it and
would mean two concurrent requests could be answered against two different indexes if the
corpus file changed underneath them.

**A refusal is a 200.** The system was asked a question and gave its honest answer, which
happens to be that it does not know. Returning 4xx would make "we have no documentation on
this" indistinguishable from "your request was malformed", and would put every gap in the
corpus into the error rate.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Any, AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from ragqa.config import MODEL, SETTINGS, Settings, load_jsonl
from ragqa.llm.recorded_client import CassetteMissError, RecordedClient
from ragqa.rag.pipeline import answer_question
from ragqa.rag.retriever import Index

logger = logging.getLogger(__name__)


class AskRequest(BaseModel):
    """A question, optionally continuing a session."""

    model_config = {"extra": "forbid"}

    question: str = Field(min_length=1, max_length=500)
    session_id: str | None = None
    user_email: str = Field(default="unknown@northwind.example", max_length=200)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the index and open the cassette set once per process."""
    settings: Settings = app.state.settings
    documents = load_jsonl(settings.corpus_path)
    app.state.index = Index.build(documents)
    app.state.client = RecordedClient(settings.cassette_dir, model=MODEL)
    logger.info(
        "indexed %d document(s) into %d chunk(s)", len(documents), len(app.state.index)
    )
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI application.

    A factory rather than a module-level singleton so a test can point an app at its own
    corpus, cassettes and database.
    """
    app = FastAPI(
        title="ragqa",
        version="0.5.0",
        summary="Answers questions about company policy from the knowledge base, or says it cannot",
        lifespan=lifespan,
    )
    app.state.settings = settings or SETTINGS
    _register_routes(app)
    return app


def get_index(request: Request) -> Index:
    """Dependency: the index built at start-up.

    Reached through ``request.app`` rather than a closure so the annotation aliases below
    can live at module scope. FastAPI resolves this module's string annotations against
    module globals, and an alias defined inside a function is invisible to it -- the
    parameter is then treated as a query parameter and every request fails with a 422.
    """
    return request.app.state.index


def get_client(request: Request) -> RecordedClient:
    """Dependency: the recorded model client."""
    return request.app.state.client


def get_settings(request: Request) -> Settings:
    """Dependency: this app's settings."""
    return request.app.state.settings


IndexDep = Annotated[Index, Depends(get_index)]
ClientDep = Annotated[RecordedClient, Depends(get_client)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _register_routes(app: FastAPI) -> None:
    """Attach every route to ``app``."""

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """Liveness. Touches nothing."""
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz(index: IndexDep, client: ClientDep) -> dict[str, Any]:
        """Readiness: the index is built and the cassette set is present."""
        chunks = len(index)
        cassettes = len(client.keys())
        body = {"chunks": chunks, "cassettes": cassettes}
        if not chunks or not cassettes:
            raise HTTPException(status_code=503, detail=body)
        return {"status": "ready", **body}

    @app.get("/v1/corpus")
    def corpus(index: IndexDep) -> dict[str, Any]:
        """What the assistant can answer from.

        Titles and ids only. Returning passage text would make this a way to read the
        whole knowledge base without asking a question, which is not what it is for.
        """
        seen: dict[str, str] = {}
        for chunk in index.chunks:
            seen.setdefault(chunk.doc_id, chunk.title)
        return {
            "documents": [{"id": k, "title": v} for k, v in sorted(seen.items())],
            "chunks": len(index),
        }

    @app.post("/v1/ask")
    def ask(
        payload: AskRequest,
        index: IndexDep,
        client: ClientDep,
        settings: SettingsDep,
    ) -> dict[str, Any]:
        """Answer a question from the knowledge base, or decline to."""
        try:
            answer = answer_question(payload.question, index=index, client=client)
        except CassetteMissError as exc:
            # 503 rather than 500: the service is configured wrongly -- the fixture set
            # and the questions it is being asked have drifted apart -- rather than
            # having hit a bug while processing a valid request.
            logger.error("cassette miss for %r", payload.question[:80])
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        session_id = payload.session_id or str(uuid.uuid4())
        try:
            from ragqa import db

            with db.connection(settings) as conn:
                db.ensure_session(conn, session_id, payload.user_email)
                db.record_message(
                    conn,
                    session_id=session_id,
                    question=payload.question,
                    answer=answer.text,
                    refused=answer.refused,
                    citations=answer.citations,
                )
        except Exception:  # noqa: BLE001 - history is useful, not load-bearing
            # The answer is already correct and the user is waiting for it. Failing the
            # request because the history write failed would turn a logging outage into
            # an assistant outage.
            logger.warning("could not record conversation turn", exc_info=True)

        return {"session_id": session_id, **answer.as_dict()}

    @app.get("/v1/sessions/{session_id}/history")
    def history(session_id: str, settings: SettingsDep, limit: int = 50) -> dict[str, Any]:
        """Return one session's conversation, newest first."""
        from ragqa import db

        with db.connection(settings) as conn:
            rows = db.session_history(conn, session_id, limit=limit)
        return {
            "session_id": session_id,
            "turns": [
                {
                    "question": row["question"],
                    "answer": row["answer"],
                    "refused": row["refused"],
                    "citations": list(row["citations"]),
                    "asked_at": row["asked_at"].isoformat(),
                }
                for row in rows
            ],
        }


#: The ASGI application uvicorn serves.
app = create_app()
