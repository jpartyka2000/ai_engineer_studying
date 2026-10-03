"""Applying the numbered SQL migrations.

Deliberately about fifty lines. A migration runner is a thing every team writes once and
then lives with, and the ones that cause trouble are the ones that got clever: ordering
by mtime, tracking by content hash, running everything every time.

The rules here:

**Filename order, zero-padded.** ``0010`` sorts after ``0009`` because the numbers are
padded, not because anything parses them.

**Applied migrations are recorded by name** in ``schema_migrations`` and never re-run.
Tracking by content hash instead would make an edit to an applied migration look like a
new one, which is the opposite of what you want -- an edit to history should be noticed,
not silently replayed.

**No down migrations.** Nothing here has ever needed one, and a down migration that has
never been run is a down migration that does not work.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlgenie.config import SETTINGS, Settings
from sqlgenie.db import pool

logger = logging.getLogger(__name__)

TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    name        TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def pending(connection, migrations_dir: Path) -> list[Path]:
    """Return the migrations not yet applied, in filename order.

    Args:
        connection: An owner connection.
        migrations_dir: Directory of ``NNNN_name.sql`` files.

    Returns:
        Paths to apply, in order.
    """
    with connection.cursor() as cursor:
        cursor.execute(TRACKING_TABLE)
        cursor.execute("SELECT name FROM schema_migrations")
        applied = {row["name"] for row in cursor.fetchall()}
    return [path for path in sorted(migrations_dir.glob("*.sql")) if path.name not in applied]


def apply_all(settings: Settings | None = None) -> list[str]:
    """Apply every pending migration.

    Args:
        settings: Override settings.

    Returns:
        The names applied, in order. Empty when the schema is already current.
    """
    resolved = settings or SETTINGS
    applied: list[str] = []
    with pool.owner_connection(resolved) as connection:
        for path in pending(connection, resolved.migrations_dir):
            logger.info("applying %s", path.name)
            with connection.cursor() as cursor:
                cursor.execute(path.read_text(encoding="utf-8"))
                cursor.execute(
                    "INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,)
                )
            applied.append(path.name)
    return applied
