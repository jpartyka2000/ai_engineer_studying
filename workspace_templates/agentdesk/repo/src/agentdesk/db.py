"""The connection pool, and the one place a connection is ever checked out.

**Every** database access in this service goes through :func:`connection`. That is not
tidiness for its own sake -- it is what makes the latency rule enforceable. The probe that
answers "was a connection held across a model call?" can only see checkouts it was told
about, so a module that reaches for ``psycopg.connect`` directly is invisible to it and
the rule silently stops applying to that module.
``tests/test_layering.py::test_every_database_access_goes_through_the_pool_helper``
scans the source for exactly that.
"""

from __future__ import annotations

import itertools
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Protocol

import psycopg
from psycopg_pool import ConnectionPool

from agentdesk.config import SETTINGS
from agentdesk.obs import db_span

logger = logging.getLogger(__name__)

#: Distinguishes one checkout from the next in a trace. A plain counter rather than a
#: uuid: traces are read by humans, and ``conn-3`` is easier to follow than a hex blob.
_tokens = itertools.count(1)


class Pool(Protocol):
    """What :func:`connection` needs from a pool.

    Narrow on purpose, so the tests that have no Postgres can supply their own object and
    still travel the real code path -- including the instrumentation, which is the part
    under test.
    """

    @contextmanager
    def connection(self) -> Iterator[Any]:  # pragma: no cover - structural
        ...


_POOL: Pool | None = None


def pool() -> Pool:
    """Return the process pool, opening it on first use.

    Opening lazily rather than at import keeps ``import agentdesk`` free of side effects,
    which is what lets the unit suite run with ``DATABASE_URL`` pointed at a dead port.
    """
    global _POOL
    if _POOL is None:
        _POOL = ConnectionPool(
            SETTINGS.database_url,
            min_size=1,
            max_size=SETTINGS.pool_max,
            # Fail rather than queue forever. A request that cannot get a connection
            # inside two seconds is already a failed request; blocking turns one slow
            # dependency into an outage across every endpoint.
            timeout=2.0,
            open=True,
        )
    return _POOL


def set_pool(replacement: Pool | None) -> None:
    """Install a pool, or ``None`` to drop back to the real one. Tests only."""
    global _POOL
    _POOL = replacement


@contextmanager
def connection() -> Iterator[Any]:
    """Check a connection out of the pool for the duration of the block.

    Keep the block **short**, and keep anything slow outside it -- a model call above all.
    The span recorded here is what the latency tests read.

    Yields:
        A live connection.
    """
    token = f"conn-{next(_tokens)}"
    with db_span(token), pool().connection() as conn:
        yield conn


def migrate() -> list[str]:
    """Apply every migration not yet recorded as applied.

    Migrations are plain numbered SQL files applied in filename order inside one
    transaction each. No framework: the schema is small, and a migration you can read in
    full is worth more here than one that is generated.

    Returns:
        The filenames applied by this call, in order.
    """
    applied: list[str] = []
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "  filename text PRIMARY KEY,"
                "  applied_at timestamptz NOT NULL DEFAULT now()"
                ")"
            )
            conn.commit()
            cur.execute("SELECT filename FROM schema_migrations")
            done = {row[0] for row in cur.fetchall()}

        for path in sorted(SETTINGS.migrations_dir.glob("*.sql")):
            if path.name in done:
                continue
            logger.info("applying migration %s", path.name)
            with conn.cursor() as cur:
                cur.execute(path.read_text(encoding="utf-8"))
                cur.execute(
                    "INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,)
                )
            conn.commit()
            applied.append(path.name)
    return applied


def healthy() -> bool:
    """Return whether the database answers a trivial query."""
    try:
        with connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone() == (1,)
    except psycopg.Error:
        return False


def migration_files() -> list[Path]:
    """Return the migration files in apply order."""
    return sorted(SETTINGS.migrations_dir.glob("*.sql"))
