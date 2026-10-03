"""The tools themselves.

All read-only. The assistant drafts replies for a human to send; it does not change ticket
state, and giving it a tool that could would be a product decision rather than a technical
one. The one thing it writes is a draft, and drafts go back through the desk's own API.

Handlers return **strings**, because what they return is shown to the model. A handler
that returned a dict would be rendered by whatever happened to stringify it, and the model
would be reading Python's ``repr`` -- which is both ugly and unstable across versions.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from agentdesk.assistant.registry import Param, Registry, ToolError, ToolSpec
from agentdesk.clock import now as _now
from agentdesk.config import SETTINGS
from agentdesk.tickets import service
from agentdesk.tickets.models import Status

#: How many results a search returns when the model does not say.
DEFAULT_SEARCH_LIMIT = 5


@lru_cache(maxsize=1)
def _articles() -> dict[str, dict]:
    """Return the knowledge base, keyed by slug.

    Read from a fixture rather than the database: these are published documents that ship
    with the application, and putting them in Postgres would mean the assistant could not
    answer a policy question while the database was down.
    """
    path = Path(SETTINGS.fixtures_dir) / "kb_articles.jsonl"
    articles: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            article = json.loads(line)
            articles[article["slug"]] = article
    return articles


def lookup_ticket(ticket_id: int) -> str:
    """Return one ticket's state as text for the model."""
    try:
        detail = service.ticket_detail(ticket_id, now=_now())
    except service.TicketNotFound as exc:
        raise ToolError(f"there is no ticket {ticket_id}") from exc

    sla = detail["sla"]
    lines = [
        f"ticket #{detail['id']}: {detail['subject']}",
        f"status: {detail['status']}  priority: {detail['priority']}",
        f"requester: {detail['requester']}  assignee: {detail['assignee'] or 'unassigned'}",
        f"opened: {detail['created_at']}",
        f"sla: {'BREACHED' if sla['breached'] else 'at risk' if sla['at_risk'] else 'ok'}"
        f" (due {sla['due_at']})",
        "",
        detail["body"],
    ]
    return "\n".join(lines)


def search_tickets(query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> str:
    """Return tickets matching a query, best first."""
    hits = service.find(query, limit=max(1, min(limit, 20)))
    if not hits:
        return f"no open tickets match {query!r}"
    return "\n".join(
        f"#{hit.ticket.id} [{hit.ticket.status}] {hit.ticket.subject} "
        f"(score {hit.score:.1f}, matched {', '.join(hit.matched)})"
        for hit in hits
    )


def requester_history(email: str) -> str:
    """Return a requester's recent tickets."""
    tickets = service.history_for(email, limit=10)
    if not tickets:
        return f"{email} has no previous tickets"
    return "\n".join(
        f"#{t.id} [{t.status}] {t.subject} ({t.created_at.date().isoformat()})"
        for t in tickets
    )


def kb_article(slug: str) -> str:
    """Return one knowledge base article."""
    article = _articles().get(slug)
    if article is None:
        raise ToolError(
            f"no article {slug!r}; available: {sorted(_articles())[:8]}..."
        )
    return f"{article['title']}\n\n{article['body']}"


def open_ticket_count(status: str = "open") -> str:
    """Return how many tickets sit in a status."""
    try:
        wanted = Status(status)
    except ValueError as exc:
        raise ToolError(
            f"{status!r} is not a status; try {[str(s) for s in Status]}"
        ) from exc
    counts = service.repository.count_by_status()
    return f"{counts.get(str(wanted), 0)} tickets are {wanted}"


#: The declared contracts. Separated from the handlers above so the contract can be read
#: in one place, which is what reviews of this file are almost always about.
SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="lookup_ticket",
        description=(
            "Fetch one ticket by its numeric id, including status, priority, SLA state "
            "and the requester's original message."
        ),
        parameters=(
            Param(
                name="ticket_id",
                type="integer",
                description="The ticket's numeric id, as it appears after the # symbol.",
            ),
        ),
        handler=lookup_ticket,
    ),
    ToolSpec(
        name="search_tickets",
        description=(
            "Search open and pending tickets by keyword. Returns the best matches with "
            "their ids, so a promising one can then be fetched with lookup_ticket."
        ),
        parameters=(
            Param(
                name="query",
                type="string",
                description="Keywords to search for. Not a question -- just the terms.",
            ),
            Param(
                name="limit",
                type="integer",
                description="How many matches to return. Defaults to 5, capped at 20.",
                required=False,
            ),
        ),
        handler=search_tickets,
    ),
    ToolSpec(
        name="requester_history",
        description=(
            "List a requester's ten most recent tickets, to see whether this problem has "
            "come up before."
        ),
        parameters=(
            Param(
                name="email",
                type="string",
                description="The requester's email address, exactly as on the ticket.",
            ),
        ),
        handler=requester_history,
    ),
    ToolSpec(
        name="kb_article",
        description=(
            "Read one published knowledge base article by its slug. Use this for policy "
            "and procedure rather than answering from memory."
        ),
        parameters=(
            Param(
                name="slug",
                type="string",
                description="The article's slug, for example 'password-reset-policy'.",
            ),
        ),
        handler=kb_article,
    ),
    ToolSpec(
        name="open_ticket_count",
        description="Count the tickets currently in a given status.",
        parameters=(
            Param(
                name="status",
                type="string",
                description="Which status to count.",
                required=False,
                enum=("open", "pending", "resolved", "closed"),
            ),
        ),
        handler=open_ticket_count,
    ),
)


def build_registry() -> Registry:
    """Return a registry holding every tool."""
    return Registry(SPECS)
