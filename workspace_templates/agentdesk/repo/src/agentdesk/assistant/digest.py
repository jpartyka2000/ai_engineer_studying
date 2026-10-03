"""The queue digest shown on the dashboard.

**This module makes no model calls, and that is its entire design constraint.**

Every ticket already carries a summary, written once at intake by
:func:`agentdesk.assistant.service.summarize_for_intake` and stored in a column. The
dashboard reads that column. It does not regenerate, refresh, or improve it.

The temptation is obvious and the failure is quiet. Generating a summary here is one line,
the page still renders, every summary still looks right -- and a fifty-row dashboard now
makes fifty model calls per view. Nothing errors. The page is just slow, in a way that
scales with the thing least likely to be in a load test: how many tickets the customer
has.

``test_the_queue_digest_makes_no_model_calls`` asserts the count is zero rather than
small, because "small" is how this comes back.
"""

from __future__ import annotations

from datetime import datetime

from agentdesk.tickets import repository, sla
from agentdesk.tickets.models import Status, Ticket

#: Rows on the dashboard. Chosen to be more than one screen, so an N+1 here is expensive
#: enough to notice in production and cheap enough to reproduce in a test.
DIGEST_ROWS = 25


def _line(ticket: Ticket, *, now: datetime) -> dict:
    """Return one dashboard row.

    The summary comes from :attr:`~agentdesk.tickets.models.Ticket.display_summary`, which
    falls back to the subject for tickets older than the summary column. A missing summary
    is **not** a reason to generate one here.
    """
    return {
        "id": ticket.id,
        "subject": ticket.subject,
        "summary": ticket.display_summary,
        "status": str(ticket.status),
        "priority": str(ticket.priority),
        "assignee": ticket.assignee,
        "breached": sla.is_breached(ticket, now=now),
        "at_risk": sla.is_at_risk(ticket, now=now),
        "remaining_seconds": int(sla.remaining(ticket, now=now).total_seconds()),
    }


def queue_digest(*, now: datetime, rows: int = DIGEST_ROWS) -> dict:
    """Return the dashboard payload: the worst tickets first, with counts.

    One database round trip, no model calls.

    Args:
        now: The instant to judge SLA state against.
        rows: How many rows to return.

    Returns:
        ``rows``, ``banner`` and ``generated_at``.
    """
    tickets = repository.list_tickets(limit=max(rows * 2, 50))
    ordered = sla.triage_order(tickets, now=now)[:rows]
    return {
        "rows": [_line(ticket, now=now) for ticket in ordered],
        "banner": sla.summarize_queue(tickets, now=now),
        "generated_at": now.isoformat(),
    }


def attention_counts(*, now: datetime) -> dict[str, int]:
    """Return the three numbers in the dashboard header."""
    tickets = repository.list_tickets(limit=500)
    live = [ticket for ticket in tickets if not ticket.status.is_terminal]
    return {
        "unassigned": sum(1 for t in live if t.assignee is None),
        "breached": sum(1 for t in live if sla.is_breached(t, now=now)),
        "awaiting_customer": sum(1 for t in live if t.status is Status.PENDING),
    }
