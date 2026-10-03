"""Where the assistant meets the request cycle.

**This module is the whole reason the desk is still fast**, and every line of it is about
spending as little of the request's two scarce resources as possible: a pooled database
connection, and the event loop thread.

The shape of every handler here is the same three beats:

1. a short database read, connection released at the end of it
2. the model call, **off** the event loop and holding nothing
3. a short database write

That ordering is not stylistic. Fold step 2 inside step 1's connection and the pool
drains under load: ten concurrent assistant requests, each holding one of ten connections
for the length of a generation, and the ticket list -- which has nothing to do with the
assistant -- starts timing out. Run step 2 on the event loop and it is worse, because then
*every* endpoint in the process stops, including the health check.

Both properties are asserted in ``tests/test_integration_latency.py``, by mechanism rather
than by stopwatch.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from agentdesk.assistant import prompt
from agentdesk.assistant.loop import Run, StepBudgetExceeded, run_agent
from agentdesk.assistant.registry import Registry
from agentdesk.assistant.tools import build_registry
from agentdesk.clock import now as _clock_now
from agentdesk.config import SETTINGS
from agentdesk.llm.recorded_client import RecordedClient
from agentdesk.tickets import repository, service as desk
from agentdesk.tickets.models import Ticket

logger = logging.getLogger(__name__)


def build_client() -> RecordedClient:
    """Return a client reading the repository's cassettes."""
    return RecordedClient(SETTINGS.cassette_dir, model=SETTINGS.model)


def _load_ticket(ticket_id: int) -> Ticket:
    """Read one ticket. Its own connection, held for one query.

    Raises:
        TicketNotFound: If no ticket has this id.
    """
    ticket = repository.get_ticket(ticket_id)
    if ticket is None:
        raise desk.TicketNotFound(f"no ticket {ticket_id}")
    return ticket


def _save_draft(ticket_id: int, run: Run) -> int:
    """Persist a draft reply and return its id. Its own connection, held for one insert."""
    from agentdesk import db

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO assistant_drafts (ticket_id, question, answer, citations, steps) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (
                ticket_id,
                run.question,
                run.answer,
                list(run.citations),
                len(run.steps),
            ),
        )
        draft_id = cur.fetchone()[0]
        conn.commit()
        return draft_id


def _draft_sync(
    question: str,
    *,
    ticket_body: str | None,
    registry: Registry | None = None,
    client: RecordedClient | None = None,
) -> Run:
    """Run the agent. Blocking, holds no connection of its own.

    Its tools open connections as they need them, each for the length of one query. That
    is fine and is the point: short, independent checkouts rather than one long one.
    """
    return run_agent(
        question,
        registry=registry or build_registry(),
        client=client or build_client(),
        ticket_body=ticket_body,
    )


async def draft_reply(
    ticket_id: int,
    question: str,
    *,
    registry: Registry | None = None,
    client: RecordedClient | None = None,
) -> dict:
    """Draft a reply to one ticket.

    Args:
        ticket_id: Ticket the question concerns.
        question: What the support agent asked.
        registry: Tools to use. Defaults to the real ones; injected by tests so the
            latency properties can be asserted without a database behind every tool.
        client: Model to use. Same reasoning.

    Returns:
        The draft, its citations and the tool calls behind it.

    Raises:
        TicketNotFound: If no such ticket exists.
    """
    # 1. Read. The connection is released when this returns, before the model is called.
    ticket = await asyncio.to_thread(_load_ticket, ticket_id)

    # 2. Generate. Off the event loop, so every other endpoint keeps being served, and
    #    holding no connection, so the pool stays available to the desk.
    try:
        run = await asyncio.to_thread(
            _draft_sync,
            question,
            ticket_body=ticket.body,
            registry=registry,
            client=client,
        )
    except StepBudgetExceeded as exc:
        logger.warning("agent gave up on ticket %s: %s", ticket_id, exc)
        return {
            "ticket_id": ticket_id,
            "question": question,
            "answer": "",
            "citations": [],
            "steps": [],
            "gave_up": True,
        }

    # 3. Write. Again its own connection, again one statement long.
    draft_id = await asyncio.to_thread(_save_draft, ticket_id, run)

    return {"draft_id": draft_id, "ticket_id": ticket_id, "gave_up": False, **run.as_dict()}


async def summarize_for_intake(
    subject: str,
    body: str,
    *,
    registry: Registry | None = None,
    client: RecordedClient | None = None,
) -> str:
    """Produce the one-line summary cached on a new ticket.

    **The only model call the desk makes per ticket, and it happens once, at creation.**
    Everything that reads a summary afterwards reads the column. See
    :mod:`agentdesk.assistant.digest` for what goes wrong when that is forgotten.
    """
    question = f"Summarize this ticket in one line for a queue listing: {subject}"
    run = await asyncio.to_thread(
        _draft_sync, question, ticket_body=body, registry=registry, client=client
    )
    return run.answer.strip()


def fence_preview(body: str) -> str:
    """Return a ticket body as the model will see it. Used by the CLI and the API's
    debug view, so an operator can confirm a suspicious ticket really was fenced."""
    return prompt.fence("ticket", body)


def now() -> datetime:
    """Return the current instant, UTC. See :mod:`agentdesk.clock`."""
    return _clock_now()
