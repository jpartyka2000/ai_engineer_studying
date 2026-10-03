"""The ticket, as the desk has modeled it since long before the assistant existed.

One field repays attention: :attr:`Ticket.summary`. It is a **cached** one-line summary,
written once when the ticket is created and read on every list view thereafter. The cache
is the entire reason the list endpoint is fast, and it is the kind of thing that gets
quietly bypassed during a refactor -- the page still renders, the summaries still look
right, and the endpoint now makes one model call per row.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class Status(StrEnum):
    """Where a ticket is in its life."""

    OPEN = "open"
    PENDING = "pending"
    RESOLVED = "resolved"
    CLOSED = "closed"

    @property
    def is_terminal(self) -> bool:
        """Whether the SLA clock has stopped."""
        return self in (Status.RESOLVED, Status.CLOSED)


class Priority(StrEnum):
    """How fast the desk has promised to respond."""

    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass(frozen=True)
class Ticket:
    """One support ticket.

    Attributes:
        id: Surrogate key, also the handle customers quote.
        subject: One line, as typed by the requester.
        body: The full request.
        status: Current state.
        priority: Drives the SLA target.
        requester: Email of whoever opened it.
        assignee: Email of the agent who owns it, or ``None`` if unassigned.
        created_at: When it arrived. Timezone-aware, always UTC.
        updated_at: Last modification.
        summary: Cached one-line summary. ``None`` only for tickets created before the
            summary column existed; the list view falls back to truncating the subject
            rather than generating one on demand.
        tags: Free-form labels.
    """

    id: int
    subject: str
    body: str
    status: Status
    priority: Priority
    requester: str
    created_at: datetime
    updated_at: datetime
    assignee: str | None = None
    summary: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __str__(self) -> str:
        return f"#{self.id} [{self.status}] {self.subject}"

    @property
    def display_summary(self) -> str:
        """The line shown in list views.

        Falls back to the subject when no summary was cached. **Never generates one** --
        a list view is not allowed to call a model, and the fallback existing is what
        makes that affordable.
        """
        if self.summary:
            return self.summary
        return self.subject if len(self.subject) <= 80 else self.subject[:77] + "..."

    def as_dict(self) -> dict:
        """Return a JSON-serializable view.

        Datetimes become ISO-8601 strings here rather than at the API boundary, so every
        caller -- the API, the CLI, the eval harness -- agrees on the shape.
        """
        return {
            "id": self.id,
            "subject": self.subject,
            "body": self.body,
            "status": str(self.status),
            "priority": str(self.priority),
            "requester": self.requester,
            "assignee": self.assignee,
            "created_at": self.created_at.astimezone(timezone.utc).isoformat(),
            "updated_at": self.updated_at.astimezone(timezone.utc).isoformat(),
            "summary": self.display_summary,
            "tags": list(self.tags),
        }
