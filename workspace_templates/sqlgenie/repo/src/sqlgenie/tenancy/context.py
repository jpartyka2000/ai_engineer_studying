"""The current tenant, carried out of band.

A ``ContextVar`` rather than a parameter threaded through every signature. The argument
for threading it is real -- an explicit parameter cannot be forgotten -- but it loses to
one practical fact: the tenant has to be available to the audit logger, the policy and
the executor, and a parameter that must be passed through six layers is a parameter that
will eventually be passed wrongly by one of them.

**What a ContextVar does and does not survive.** It is bound per task and inherited by
code the task awaits, which covers an ordinary request. It is **not** inherited by work
handed to a thread pool or a new event loop, because those start from a fresh context. So
any boundary that leaves the request's task has to carry the tenant across deliberately,
and :func:`bind_tenant` exists to make that an obvious two-line operation rather than
something people reinvent.

:func:`require_tenant` raises rather than returning ``None``. Every caller is about to
build or run a query, and "no tenant" is never a query that should run.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator

#: The tenant the current request belongs to. Unset outside a request, which is the
#: correct state for a background job that has not chosen one.
_current_tenant: ContextVar[str | None] = ContextVar("current_tenant", default=None)


class NoTenantError(RuntimeError):
    """Raised when tenant-scoped work is attempted with no tenant bound.

    Fatal by design. The alternatives are to pick a tenant (wrong) or to run without a
    predicate (much worse), and neither belongs in a service whose whole job is keeping
    customers' data apart.
    """


def current_tenant() -> str | None:
    """Return the bound tenant, or ``None``."""
    return _current_tenant.get()


def require_tenant() -> str:
    """Return the bound tenant, or raise.

    Returns:
        The tenant id.

    Raises:
        NoTenantError: If no tenant is bound.
    """
    tenant = _current_tenant.get()
    if tenant is None:
        raise NoTenantError(
            "no tenant is bound to this context. A query was about to be built without "
            "one, which would either fail or -- worse -- succeed unscoped."
        )
    return tenant


def set_tenant(tenant_id: str) -> Token:
    """Bind a tenant, returning the token needed to unbind it.

    Prefer :func:`bind_tenant`, which cannot be left dangling.
    """
    return _current_tenant.set(tenant_id)


def reset_tenant(token: Token) -> None:
    """Unbind, restoring whatever was bound before."""
    _current_tenant.reset(token)


@contextmanager
def bind_tenant(tenant_id: str) -> Iterator[str]:
    """Bind a tenant for the duration of a block.

    Resets on the way out even if the block raises, so a failed request cannot leave its
    tenant bound for whatever reuses the context next -- which, in a server, is another
    customer's request.

    Args:
        tenant_id: The tenant to bind.

    Yields:
        The bound tenant id.
    """
    token = _current_tenant.set(tenant_id)
    try:
        yield tenant_id
    finally:
        _current_tenant.reset(token)
