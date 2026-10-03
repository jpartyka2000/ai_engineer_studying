"""The desk itself: SLA arithmetic, search ranking, and the summary cache.

None of this needs a model and none of it needs a database. That is the point of the
layering, and these tests are the evidence that it holds in practice rather than only in
the import graph.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agentdesk.tickets import search, sla
from agentdesk.tickets.models import Priority, Status, Ticket

NOW = datetime(2025, 6, 18, 9, 0, tzinfo=timezone.utc)


def ticket(
    ticket_id: int = 1,
    *,
    priority: Priority = Priority.NORMAL,
    status: Status = Status.OPEN,
    age: timedelta = timedelta(0),
    subject: str = "VPN will not connect",
    body: str = "I cannot reach the VPN from home.",
    summary: str | None = None,
) -> Ticket:
    created = NOW - age
    return Ticket(
        id=ticket_id,
        subject=subject,
        body=body,
        status=status,
        priority=priority,
        requester="dana@example.com",
        created_at=created,
        updated_at=created,
        summary=summary,
    )


def test_each_priority_has_its_own_target() -> None:
    assert sla.target(Priority.URGENT) == timedelta(minutes=30)
    assert sla.target(Priority.LOW) == timedelta(hours=48)


def test_a_ticket_past_its_target_has_breached() -> None:
    assert sla.is_breached(ticket(priority=Priority.URGENT, age=timedelta(hours=1)), now=NOW)


def test_a_resolved_ticket_never_breaches() -> None:
    """The clock stops when the desk responds, however late the response was."""
    old = ticket(priority=Priority.URGENT, age=timedelta(days=5), status=Status.RESOLVED)
    assert not sla.is_breached(old, now=NOW)


def test_at_risk_excludes_what_has_already_breached() -> None:
    """Lumping the two together makes breached tickets harder to find, not easier."""
    breached = ticket(1, priority=Priority.URGENT, age=timedelta(hours=1))
    close = ticket(2, priority=Priority.URGENT, age=timedelta(minutes=25))
    assert sla.is_breached(breached, now=NOW) and not sla.is_at_risk(breached, now=NOW)
    assert sla.is_at_risk(close, now=NOW) and not sla.is_breached(close, now=NOW)


def test_remaining_keeps_its_sign() -> None:
    """A two-day breach must not read the same as an on-time response."""
    late = ticket(priority=Priority.URGENT, age=timedelta(hours=2))
    assert sla.remaining(late, now=NOW) < timedelta(0)


def test_triage_puts_breached_first_then_at_risk() -> None:
    fresh = ticket(1, priority=Priority.LOW)
    breached = ticket(2, priority=Priority.URGENT, age=timedelta(hours=2))
    at_risk = ticket(3, priority=Priority.URGENT, age=timedelta(minutes=26))

    assert [t.id for t in sla.triage_order([fresh, breached, at_risk], now=NOW)] == [2, 3, 1]


def test_triage_order_is_total() -> None:
    """Two identical tickets must not swap places between two identical requests."""
    pair = [ticket(7, age=timedelta(hours=1)), ticket(3, age=timedelta(hours=1))]
    assert [t.id for t in sla.triage_order(pair, now=NOW)] == [3, 7]
    assert [t.id for t in sla.triage_order(list(reversed(pair)), now=NOW)] == [3, 7]


def test_triage_drops_terminal_tickets() -> None:
    closed = ticket(1, status=Status.CLOSED)
    assert sla.triage_order([closed], now=NOW) == []


def test_the_queue_banner_counts_what_it_says() -> None:
    tickets = [
        ticket(1, priority=Priority.URGENT, age=timedelta(hours=2)),
        ticket(2, status=Status.PENDING),
        ticket(3, status=Status.CLOSED),
    ]
    banner = sla.summarize_queue(tickets, now=NOW)
    assert banner == {"total": 3, "open": 1, "pending": 1, "breached": 1, "at_risk": 0}


def test_a_cached_summary_is_used_verbatim() -> None:
    assert ticket(summary="Cannot reach VPN.").display_summary == "Cannot reach VPN."


def test_a_missing_summary_falls_back_to_the_subject() -> None:
    """**Load-bearing.** This fallback is what makes it affordable for a list view never
    to call a model, including for the tickets that predate the summary column."""
    assert ticket(summary=None).display_summary == "VPN will not connect"


def test_a_long_subject_is_truncated_rather_than_summarized() -> None:
    long = "x" * 200
    assert ticket(subject=long, summary=None).display_summary.endswith("...")
    assert len(ticket(subject=long, summary=None).display_summary) == 80


def test_a_ticket_serializes_with_iso_timestamps() -> None:
    payload = ticket().as_dict()
    assert payload["created_at"].endswith("+00:00")
    assert payload["status"] == "open"


def test_search_weights_the_subject_above_the_body() -> None:
    in_subject = ticket(1, subject="printer jams", body="unrelated text")
    in_body = ticket(2, subject="unrelated text", body="printer jams")
    hits = search.rank([in_body, in_subject], "printer")
    assert [hit.ticket.id for hit in hits] == [1, 2]


def test_search_ignores_stopwords() -> None:
    """Otherwise "the printer issue" ranks every ticket containing "the"."""
    assert search.tokenize("the printer is in the office") == ["printer", "office"]


def test_a_query_of_only_stopwords_matches_nothing() -> None:
    assert search.rank([ticket()], "the and is") == []


def test_search_reports_which_terms_matched() -> None:
    hits = search.rank([ticket(subject="vpn drops", body="every twenty minutes")], "vpn minutes")
    assert set(hits[0].matched) == {"vpn", "minutes"}


def test_search_ties_break_by_id() -> None:
    first = ticket(9, subject="printer jams")
    second = ticket(4, subject="printer jams")
    assert [hit.ticket.id for hit in search.rank([first, second], "printer")] == [4, 9]


@pytest.mark.parametrize("status", list(Status))
def test_terminal_states_are_exactly_resolved_and_closed(status: Status) -> None:
    assert status.is_terminal == (status in (Status.RESOLVED, Status.CLOSED))
