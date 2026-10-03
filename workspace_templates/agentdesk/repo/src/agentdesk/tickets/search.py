"""Ranking for ticket search.

Pure functions over tickets already in memory. The desk has a few thousand live tickets,
so the database does the filtering and this does the ordering -- which keeps the ranking
rules readable and, more usefully, testable without a database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agentdesk.tickets.models import Ticket

#: Subject matches count for more than body matches. A requester writes the subject line
#: to be found; the body is where they explain.
SUBJECT_WEIGHT = 3.0
BODY_WEIGHT = 1.0

#: Words carried by nearly every ticket, which therefore separate nothing. Dropping them
#: stops "the printer issue" from ranking every ticket containing "the".
STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from", "has",
        "have", "i", "in", "is", "it", "its", "me", "my", "not", "of", "on", "or",
        "that", "the", "this", "to", "was", "we", "with", "you", "your",
    }
)

_WORD = re.compile(r"[a-z0-9']+")


def tokenize(text: str) -> list[str]:
    """Split text into lowercase word tokens, stopwords removed."""
    return [word for word in _WORD.findall(text.lower()) if word not in STOPWORDS]


@dataclass(frozen=True)
class Hit:
    """One search result.

    Attributes:
        ticket: The matching ticket.
        score: Weighted term overlap. Comparable only within one search.
        matched: The query terms that actually appeared, which is what the UI highlights.
    """

    ticket: Ticket
    score: float
    matched: tuple[str, ...]


def score(ticket: Ticket, terms: list[str]) -> tuple[float, tuple[str, ...]]:
    """Return a ticket's score for a query and the terms it matched."""
    subject_terms = set(tokenize(ticket.subject))
    body_terms = set(tokenize(ticket.body))

    total = 0.0
    matched: list[str] = []
    for term in terms:
        in_subject = term in subject_terms
        in_body = term in body_terms
        if in_subject:
            total += SUBJECT_WEIGHT
        if in_body:
            total += BODY_WEIGHT
        if in_subject or in_body:
            matched.append(term)
    return total, tuple(matched)


def rank(tickets: list[Ticket], query: str, *, limit: int = 10) -> list[Hit]:
    """Return the best matches for a query, highest score first.

    Ties break by id so the order is total: two tickets with identical scores must not
    swap places between two identical requests.

    Args:
        tickets: Candidates, already filtered by whatever the caller cared about.
        query: Raw user query.
        limit: Most hits to return.

    Returns:
        At most ``limit`` hits, each with a non-zero score.
    """
    terms = tokenize(query)
    if not terms:
        return []

    hits: list[Hit] = []
    for ticket in tickets:
        value, matched = score(ticket, terms)
        if value > 0:
            hits.append(Hit(ticket=ticket, score=value, matched=matched))

    hits.sort(key=lambda hit: (-hit.score, hit.ticket.id))
    return hits[:limit]
