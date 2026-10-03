"""Business logic for the desk.

**This package does not import** :mod:`agentdesk.assistant`, and the import-direction test
in ``tests/test_layering.py`` enforces it. The desk predates the assistant by three years
and has to keep working when the assistant is down, which is only true if it cannot reach
it. Anything here that looks like it wants a model -- a summary, a suggested reply --
takes it as an argument instead, supplied by a caller that is allowed to produce one.
"""

from __future__ import annotations

from datetime import datetime

from agentdesk.tickets import repository, search, sla
from agentdesk.tickets.models import Priority, Status, Ticket


class TicketNotFound(LookupError):
    """Raised when an operation names a ticket id that does not exist."""


def queue_page(
    *,
    now: datetime,
    status: Status | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Return one page of the queue, with the SLA banner.

    **One database round trip, zero model calls.** Summaries are read from the column;
    see :attr:`~agentdesk.tickets.models.Ticket.display_summary` for the fallback when a
    ticket predates the cache.
    """
    tickets = repository.list_tickets(status=status, limit=limit, offset=offset)
    ordered = sla.triage_order(tickets, now=now) + [
        t for t in tickets if t.status.is_terminal
    ]
    return {
        "tickets": [t.as_dict() for t in ordered],
        "banner": sla.summarize_queue(tickets, now=now),
        "limit": limit,
        "offset": offset,
    }


def ticket_detail(ticket_id: int, *, now: datetime) -> dict:
    """Return one ticket with its SLA state.

    Raises:
        TicketNotFound: If no ticket has this id.
    """
    ticket = repository.get_ticket(ticket_id)
    if ticket is None:
        raise TicketNotFound(f"no ticket {ticket_id}")
    return {
        **ticket.as_dict(),
        "sla": {
            "due_at": sla.due_at(ticket).isoformat(),
            "remaining_seconds": int(sla.remaining(ticket, now=now).total_seconds()),
            "breached": sla.is_breached(ticket, now=now),
            "at_risk": sla.is_at_risk(ticket, now=now),
        },
    }


def open_ticket(
    *,
    subject: str,
    body: str,
    requester: str,
    priority: Priority = Priority.NORMAL,
    summary: str | None = None,
    tags: tuple[str, ...] = (),
) -> Ticket:
    """Create a ticket.

    Args:
        summary: A pre-computed one-line summary, or ``None``. This function never
            generates one -- that needs a model, and the desk does not call models. The
            intake path supplies it; see :mod:`agentdesk.assistant.service`.
    """
    if not subject.strip():
        raise ValueError("a ticket needs a subject")
    return repository.create_ticket(
        subject=subject.strip(),
        body=body,
        requester=requester,
        priority=priority,
        summary=summary,
        tags=tags,
    )


def resolve(ticket_id: int) -> Ticket:
    """Mark a ticket resolved, stopping its SLA clock.

    Raises:
        TicketNotFound: If no ticket has this id.
    """
    ticket = repository.set_status(ticket_id, Status.RESOLVED)
    if ticket is None:
        raise TicketNotFound(f"no ticket {ticket_id}")
    return ticket


def assign_to(ticket_id: int, assignee: str | None) -> Ticket:
    """Set or clear a ticket's owner.

    Raises:
        TicketNotFound: If no ticket has this id.
    """
    ticket = repository.assign(ticket_id, assignee)
    if ticket is None:
        raise TicketNotFound(f"no ticket {ticket_id}")
    return ticket


def find(query: str, *, limit: int = 10) -> list[search.Hit]:
    """Search open and pending tickets.

    Terminal tickets are excluded: the desk searches to find work, and a resolved ticket
    is not work. History lives behind :func:`history_for`.
    """
    candidates = [
        t
        for t in repository.list_tickets(limit=500)
        if not t.status.is_terminal
    ]
    return search.rank(candidates, query, limit=limit)


def history_for(requester: str, *, limit: int = 20) -> list[Ticket]:
    """Return a requester's recent tickets, newest first."""
    return repository.by_requester(requester, limit=limit)
