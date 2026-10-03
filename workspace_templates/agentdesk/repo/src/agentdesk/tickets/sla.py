"""Response-time targets, as pure arithmetic.

No database, no clock of its own: every function takes ``now`` as an argument. That is
what lets the whole policy be tested with exact values instead of sleeps, and it is the
reason this module has never been the cause of a flaky test.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from agentdesk.tickets.models import Priority, Status, Ticket

#: Minutes the desk has promised, by priority. Contractual numbers; changing one is a
#: commercial decision, not an engineering one.
TARGET_MINUTES: dict[Priority, int] = {
    Priority.URGENT: 30,
    Priority.HIGH: 120,
    Priority.NORMAL: 8 * 60,
    Priority.LOW: 48 * 60,
}

#: Fraction of the target at which a ticket starts being reported as at risk. Chosen so
#: an urgent ticket raises its hand at 24 minutes, which is early enough to act on.
AT_RISK_FRACTION = 0.8


def target(priority: Priority) -> timedelta:
    """Return the promised response time for a priority."""
    return timedelta(minutes=TARGET_MINUTES[priority])


def due_at(ticket: Ticket) -> datetime:
    """Return the instant this ticket's response target expires."""
    return ticket.created_at + target(ticket.priority)


def remaining(ticket: Ticket, *, now: datetime) -> timedelta:
    """Return the time left before the target expires.

    Negative once the target has passed. Callers that want "zero rather than negative"
    should clamp at the call site; swallowing the sign here would make a two-day breach
    indistinguishable from an on-time response.
    """
    return due_at(ticket) - now


def is_breached(ticket: Ticket, *, now: datetime) -> bool:
    """Return whether this ticket has missed its target.

    A resolved or closed ticket is never breached, regardless of when it was answered.
    The SLA is a promise about responding, and the clock stops when the desk responds.
    """
    if ticket.status.is_terminal:
        return False
    return remaining(ticket, now=now) < timedelta(0)


def is_at_risk(ticket: Ticket, *, now: datetime) -> bool:
    """Return whether this ticket is close enough to its target to warrant attention.

    Deliberately **excludes** tickets that have already breached: a breach is its own,
    louder state, and a queue view that lumps the two together makes the breached ones
    harder to find rather than easier.
    """
    if ticket.status.is_terminal or is_breached(ticket, now=now):
        return False
    elapsed = now - ticket.created_at
    return elapsed >= target(ticket.priority) * AT_RISK_FRACTION


def triage_order(tickets: list[Ticket], *, now: datetime) -> list[Ticket]:
    """Return tickets in the order the desk should work them.

    Breached first, then at risk, then everything else; within a band, least time
    remaining first, and ties broken by id so the order is total and the page does not
    reshuffle between requests.
    """

    def key(ticket: Ticket) -> tuple[int, float, int]:
        if is_breached(ticket, now=now):
            band = 0
        elif is_at_risk(ticket, now=now):
            band = 1
        else:
            band = 2
        return (band, remaining(ticket, now=now).total_seconds(), ticket.id)

    return sorted((t for t in tickets if not t.status.is_terminal), key=key)


def summarize_queue(tickets: list[Ticket], *, now: datetime) -> dict[str, int]:
    """Return counts for the queue banner."""
    live = [t for t in tickets if not t.status.is_terminal]
    return {
        "total": len(tickets),
        "open": sum(1 for t in live if t.status is Status.OPEN),
        "pending": sum(1 for t in live if t.status is Status.PENDING),
        "breached": sum(1 for t in live if is_breached(t, now=now)),
        "at_risk": sum(1 for t in live if is_at_risk(t, now=now)),
    }
