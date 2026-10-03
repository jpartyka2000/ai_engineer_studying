"""Turning an API key into a tenant.

The key is never stored and never compared. What is stored is its SHA-256, and lookup is
a primary-key hit on that hash -- so there is no comparison loop to be timed, and a dump
of ``api_keys`` yields no working credential.

The lookup uses the **owner** connection, not the application one, because
``sqlgenie_app`` is explicitly denied ``api_keys``. That denial is worth keeping even
though it costs a second connection: the role that executes model-generated SQL should
not be able to read the credential table under any circumstances, including ones nobody
has thought of.
"""

from __future__ import annotations

import hashlib
import logging

from sqlgenie.config import SETTINGS, Settings
from sqlgenie.db import pool

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when a key is absent, unknown or revoked.

    One exception type for all three, and the API maps it to one message. Telling a
    caller whether a key is *unknown* or merely *revoked* confirms which keys once
    existed, which is a slow enumeration oracle and buys the legitimate caller nothing.
    """


def key_digest(api_key: str) -> str:
    """Return the stored form of an API key."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def resolve_tenant(api_key: str | None, settings: Settings | None = None) -> str:
    """Resolve an API key to a tenant id.

    Args:
        api_key: The raw key from the request header.
        settings: Override settings.

    Returns:
        The tenant id.

    Raises:
        AuthenticationError: If the key is missing, unknown or revoked.
    """
    if not api_key:
        raise AuthenticationError("an API key is required")

    resolved = settings or SETTINGS
    digest = key_digest(api_key)
    with pool.owner_connection(resolved) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT tenant_id, revoked_at FROM api_keys WHERE key_sha256 = %s",
            (digest,),
        )
        row = cursor.fetchone()

    if row is None or row["revoked_at"] is not None:
        logger.warning("rejected an API key ending %s", api_key[-4:])
        raise AuthenticationError("unknown or revoked API key")
    return str(row["tenant_id"])
