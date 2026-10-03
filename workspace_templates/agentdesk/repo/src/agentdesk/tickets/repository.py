"""SQL for the ticket store.

Every query names its columns explicitly and in the same order, so :func:`_row_to_ticket`
can be positional and a column added to the table cannot silently shift a field. ``SELECT *``
is what makes that kind of bug possible, which is why it does not appear here.
"""

from __future__ import annotations

from datetime import datetime, timezone

from agentdesk import db
from agentdesk.tickets.models import Priority, Status, Ticket

#: The column list, written once. Any query returning a ticket uses this exact order.
COLUMNS = (
    "id, subject, body, status, priority, requester, assignee, "
    "created_at, updated_at, summary, tags"
)


def _row_to_ticket(row: tuple) -> Ticket:
    """Map one row, in :data:`COLUMNS` order, to a :class:`Ticket`."""
    return Ticket(
        id=row[0],
        subject=row[1],
        body=row[2],
        status=Status(row[3]),
        priority=Priority(row[4]),
        requester=row[5],
        assignee=row[6],
        created_at=_utc(row[7]),
        updated_at=_utc(row[8]),
        summary=row[9],
        tags=tuple(row[10] or ()),
    )


def _utc(value: datetime) -> datetime:
    """Return ``value`` as an aware UTC datetime.

    Postgres hands back aware values for ``timestamptz``; a naive one means somebody
    changed the column type, and treating it as UTC rather than crashing keeps the desk
    serving while that gets sorted out.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def list_tickets(*, status: Status | None = None, limit: int = 50, offset: int = 0) -> list[Ticket]:
    """Return a page of tickets, newest first.

    One query, one round trip, summaries included. The summary comes from the column --
    this function does not know the assistant exists and must not learn.
    """
    clauses = []
    params: list[object] = []
    if status is not None:
        clauses.append("status = %s")
        params.append(str(status))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {COLUMNS} FROM tickets {where} "
            "ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
            params,
        )
        return [_row_to_ticket(row) for row in cur.fetchall()]


def get_ticket(ticket_id: int) -> Ticket | None:
    """Return one ticket, or ``None`` if no such id exists."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {COLUMNS} FROM tickets WHERE id = %s", (ticket_id,))
        row = cur.fetchone()
        return _row_to_ticket(row) if row else None


def create_ticket(
    *,
    subject: str,
    body: str,
    requester: str,
    priority: Priority = Priority.NORMAL,
    summary: str | None = None,
    tags: tuple[str, ...] = (),
) -> Ticket:
    """Insert a ticket and return it as stored."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tickets (subject, body, status, priority, requester, summary, tags) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
            f"RETURNING {COLUMNS}",
            (subject, body, str(Status.OPEN), str(priority), requester, summary, list(tags)),
        )
        row = cur.fetchone()
        conn.commit()
        return _row_to_ticket(row)


def set_status(ticket_id: int, status: Status) -> Ticket | None:
    """Move a ticket to ``status`` and return it, or ``None`` if it does not exist."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE tickets SET status = %s, updated_at = now() WHERE id = %s "
            f"RETURNING {COLUMNS}",
            (str(status), ticket_id),
        )
        row = cur.fetchone()
        conn.commit()
        return _row_to_ticket(row) if row else None


def assign(ticket_id: int, assignee: str | None) -> Ticket | None:
    """Set or clear a ticket's owner."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE tickets SET assignee = %s, updated_at = now() WHERE id = %s "
            f"RETURNING {COLUMNS}",
            (assignee, ticket_id),
        )
        row = cur.fetchone()
        conn.commit()
        return _row_to_ticket(row) if row else None


def by_requester(requester: str, *, limit: int = 20) -> list[Ticket]:
    """Return a requester's tickets, newest first."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {COLUMNS} FROM tickets WHERE requester = %s "
            "ORDER BY created_at DESC, id DESC LIMIT %s",
            (requester, limit),
        )
        return [_row_to_ticket(row) for row in cur.fetchall()]


def count_by_status() -> dict[str, int]:
    """Return ticket counts grouped by status."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT status, count(*) FROM tickets GROUP BY status")
        return {row[0]: row[1] for row in cur.fetchall()}
