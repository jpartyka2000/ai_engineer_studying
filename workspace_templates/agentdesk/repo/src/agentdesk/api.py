"""HTTP surface.

**Every request-body model and every dependency lives at module scope**, and that is not
a style preference. This module uses ``from __future__ import annotations``, so FastAPI
resolves annotations against the **module globals**. A Pydantic model or an
``Annotated[...]`` alias defined inside a function is invisible to it: the parameter
silently stops being a body and becomes a query parameter, and every request to that
endpoint returns 422 with a validation error that names a field you did not write.

It costs an afternoon the first time. Keep them up here.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agentdesk import __version__, db
from agentdesk.assistant import digest, service as assistant
from agentdesk.clock import is_pinned, now
from agentdesk.config import SETTINGS
from agentdesk.serving import DESK_8B, Request as ServingRequest, Scheduler, plan_budget
from agentdesk.tickets import service as desk
from agentdesk.tickets.models import Priority, Status

logger = logging.getLogger(__name__)

app = FastAPI(
    title="agentdesk",
    version=__version__,
    description="Support ticket desk, with an assistant bolted on three years later.",
)


class NewTicket(BaseModel):
    """Body for ``POST /tickets``."""

    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    requester: str = Field(min_length=3)
    priority: Priority = Priority.NORMAL


class DraftRequest(BaseModel):
    """Body for ``POST /assistant/draft``."""

    ticket_id: int = Field(ge=1)
    question: str = Field(min_length=1, max_length=500)


class CapacityRequest(BaseModel):
    """Body for ``POST /serving/admit``."""

    prompt_tokens: int = Field(ge=1, le=8192)
    max_new_tokens: int = Field(ge=1, le=4096)
    concurrent: int = Field(default=1, ge=1, le=512)


@app.get("/health")
def health() -> dict:
    """Liveness and the two facts that most often explain a confusing failure."""
    return {
        "status": "ok",
        "version": __version__,
        "database": db.healthy(),
        "clock_pinned": is_pinned(),
    }


@app.get("/tickets")
def list_tickets(status: Status | None = None, limit: int = 50, offset: int = 0) -> dict:
    """A page of the queue, worst first. No model calls."""
    return desk.queue_page(now=now(), status=status, limit=min(limit, 200), offset=offset)


@app.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: int) -> dict:
    """One ticket with its SLA state."""
    try:
        return desk.ticket_detail(ticket_id, now=now())
    except desk.TicketNotFound:
        raise HTTPException(status_code=404, detail=f"no ticket {ticket_id}") from None


@app.post("/tickets", status_code=201)
async def create_ticket(payload: NewTicket) -> dict:
    """Open a ticket, summarizing it once on the way in.

    The summary is generated **here and only here**. Everything downstream reads the
    column; see :mod:`agentdesk.assistant.digest`.
    """
    summary = await assistant.summarize_for_intake(payload.subject, payload.body)
    ticket = desk.open_ticket(
        subject=payload.subject,
        body=payload.body,
        requester=payload.requester,
        priority=payload.priority,
        summary=summary,
    )
    return ticket.as_dict()


@app.get("/search")
def search_tickets(q: str, limit: int = 10) -> dict:
    """Keyword search over live tickets."""
    hits = desk.find(q, limit=min(limit, 50))
    return {
        "query": q,
        "hits": [
            {"ticket": hit.ticket.as_dict(), "score": hit.score, "matched": list(hit.matched)}
            for hit in hits
        ],
    }


@app.get("/dashboard")
def dashboard(rows: int = digest.DIGEST_ROWS) -> dict:
    """The queue digest. One query, no model calls, at any page size."""
    return digest.queue_digest(now=now(), rows=min(rows, 100))


@app.post("/assistant/draft")
async def draft(payload: DraftRequest) -> dict:
    """Draft a reply to a ticket."""
    try:
        return await assistant.draft_reply(payload.ticket_id, payload.question)
    except desk.TicketNotFound:
        raise HTTPException(
            status_code=404, detail=f"no ticket {payload.ticket_id}"
        ) from None


@app.get("/assistant/fence-preview/{ticket_id}")
def fence_preview(ticket_id: int) -> dict:
    """Show a ticket body exactly as the model will see it.

    Exists so that when a ticket looks like an injection attempt, an operator can confirm
    it was fenced rather than take it on trust.
    """
    try:
        detail = desk.ticket_detail(ticket_id, now=now())
    except desk.TicketNotFound:
        raise HTTPException(status_code=404, detail=f"no ticket {ticket_id}") from None
    return {"ticket_id": ticket_id, "as_the_model_sees_it": assistant.fence_preview(detail["body"])}


@app.get("/serving/plan")
def serving_plan() -> dict:
    """How the card divides up for the model this desk serves."""
    budget = plan_budget(DESK_8B, vram_bytes=SETTINGS.vram_bytes)
    scheduler = Scheduler(DESK_8B, budget=budget)
    return {
        "model": str(DESK_8B),
        "vram_bytes": budget.total,
        "weight_bytes": budget.weights,
        "reserved_bytes": budget.reserved,
        "kv_available_bytes": budget.kv_available,
        "utilization": round(budget.utilization, 4),
        **scheduler.snapshot(),
    }


@app.post("/serving/admit")
def serving_admit(payload: CapacityRequest) -> dict:
    """Ask how many requests of a given shape the card would accept.

    A planning endpoint: it admits against a fresh scheduler and reports the verdict, so
    capacity questions can be answered without putting load on the real one.
    """
    budget = plan_budget(DESK_8B, vram_bytes=SETTINGS.vram_bytes)
    scheduler = Scheduler(DESK_8B, budget=budget)

    verdicts = []
    for index in range(payload.concurrent):
        admission = scheduler.admit(
            ServingRequest(
                request_id=f"plan-{index}",
                prompt_tokens=payload.prompt_tokens,
                max_new_tokens=payload.max_new_tokens,
            )
        )
        verdicts.append({"request": admission.request_id, "verdict": str(admission.verdict)})
        if not admission.admitted:
            break

    admitted = sum(1 for v in verdicts if v["verdict"] == "admitted")
    return {
        "requested": payload.concurrent,
        "admitted": admitted,
        "verdicts": verdicts,
        "snapshot": scheduler.snapshot(),
    }
