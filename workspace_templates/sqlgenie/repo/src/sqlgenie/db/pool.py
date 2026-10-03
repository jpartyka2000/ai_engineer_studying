"""Connections, and which role they use.

Two factories, because this service legitimately needs two different identities and
conflating them is how row-level security gets switched off by accident.

:func:`app_connection` is the one that answers questions. It connects as
``sqlgenie_app``, which owns nothing, so the RLS policies on the fact tables apply to it
unconditionally.

:func:`owner_connection` is for migrations and for the authentication lookup, which has
to read ``api_keys`` -- a table the application role is explicitly denied. It is not a
general-purpose escape hatch, and the only call sites are the two named here.

**Every request runs in a transaction.** Not for atomicity -- these are reads -- but
because ``SET LOCAL`` and ``set_config(..., true)`` are scoped to one, and both the
statement timeout and the tenant setting must not survive into whatever uses this
connection next.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

from sqlgenie.config import SETTINGS, Settings

logger = logging.getLogger(__name__)


@contextmanager
def app_connection(settings: Settings | None = None) -> Iterator[Any]:
    """Open a transaction as the restricted application role.

    Yields:
        A psycopg connection inside a transaction, rolled back on the way out.

    Raises:
        RuntimeError: If the database is unreachable, with the role named -- a
            permissions failure here and a network failure here look identical in
            psycopg's message, and the distinction matters.
    """
    import psycopg
    from psycopg.rows import dict_row

    resolved = settings or SETTINGS
    try:
        connection = psycopg.connect(resolved.database_url, row_factory=dict_row)
    except psycopg.OperationalError as exc:
        raise RuntimeError(f"could not connect as the application role: {exc}") from exc

    connection.autocommit = False
    try:
        yield connection
        # Reads only: rolling back rather than committing means a generated statement
        # that somehow mutated something cannot persist it.
        connection.rollback()
    finally:
        connection.close()


@contextmanager
def owner_connection(settings: Settings | None = None) -> Iterator[Any]:
    """Open a connection as the owner role, for migrations and key lookup.

    Yields:
        A psycopg connection with autocommit on, which migrations need because some
        statements cannot run inside a transaction block.
    """
    import psycopg
    from psycopg.rows import dict_row

    resolved = settings or SETTINGS
    try:
        connection = psycopg.connect(resolved.migration_url, row_factory=dict_row)
    except psycopg.OperationalError as exc:
        raise RuntimeError(f"could not connect as the owner role: {exc}") from exc

    connection.autocommit = True
    try:
        yield connection
    finally:
        connection.close()
