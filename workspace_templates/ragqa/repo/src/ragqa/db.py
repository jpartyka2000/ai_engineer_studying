"""Postgres: connections, migrations and conversation history.

One module rather than a package, because there is not much here. The assistant answers
statelessly -- every question is retrieved and answered on its own -- so the database
holds the record of what was said rather than anything the next answer depends on.

That record earns its place three ways: somebody has to be able to see what the assistant
told an employee, the evaluation set grows by harvesting questions people actually asked,
and a rising refusal rate is the earliest signal that the corpus has a gap.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from ragqa.config import SETTINGS, Settings

logger = logging.getLogger(__name__)

TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    name        TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


@contextmanager
def connection(settings: Settings | None = None) -> Iterator[Any]:
    """Open a connection, committing on success and rolling back on error.

    Yields:
        A psycopg connection with dict rows.

    Raises:
        RuntimeError: If the database is unreachable, naming the URL's host so a
            connection failure is distinguishable from a credentials failure.
    """
    import psycopg
    from psycopg.rows import dict_row

    resolved = settings or SETTINGS
    try:
        conn = psycopg.connect(resolved.database_url, row_factory=dict_row)
    except psycopg.OperationalError as exc:
        raise RuntimeError(f"could not connect to Postgres: {exc}") from exc

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate(settings: Settings | None = None) -> list[str]:
    """Apply pending migrations in filename order.

    Applied migrations are recorded by name and never re-run. Tracking by content hash
    instead would make an edit to an applied migration look like a new one, which is the
    opposite of useful -- an edit to history should be noticed, not replayed.

    Args:
        settings: Override settings.

    Returns:
        The migration names applied, in order.
    """
    resolved = settings or SETTINGS
    directory = resolved.root / "db" / "migrations"
    applied: list[str] = []

    with connection(resolved) as conn, conn.cursor() as cursor:
        cursor.execute(TRACKING_TABLE)
        cursor.execute("SELECT name FROM schema_migrations")
        done = {row["name"] for row in cursor.fetchall()}
        for path in sorted(directory.glob("*.sql")):
            if path.name in done:
                continue
            logger.info("applying %s", path.name)
            cursor.execute(path.read_text(encoding="utf-8"))
            cursor.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
            applied.append(path.name)
    return applied


def ensure_session(conn: Any, session_id: str, user_email: str) -> None:
    """Create a session row if it does not already exist."""
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO sessions (id, user_email) VALUES (%s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (session_id, user_email),
        )


def record_message(
    conn: Any,
    *,
    session_id: str,
    question: str,
    answer: str,
    refused: bool,
    citations: Sequence[str],
) -> None:
    """Append one question-and-answer turn to a session."""
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO messages (session_id, question, answer, refused, citations)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (session_id, question, answer, refused, list(citations)),
        )


def session_history(conn: Any, session_id: str, *, limit: int = 50) -> list[dict]:
    """Return one session's turns, newest first.

    Args:
        conn: An open connection.
        session_id: The session to read.
        limit: Maximum turns to return.

    Returns:
        Message rows for **that session only**. The filter is the whole point: a
        conversation with an internal assistant is a list of the things somebody did not
        know, which is not a list they would choose to share with colleagues.
    """
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT session_id, question, answer, refused, citations, asked_at
            FROM messages
            WHERE session_id = %s
            ORDER BY asked_at DESC
            LIMIT %s
            """,
            (session_id, limit),
        )
        return list(cursor.fetchall())
