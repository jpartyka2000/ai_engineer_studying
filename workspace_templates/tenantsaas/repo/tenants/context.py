"""Request-scoped tenant context.

Held in a :class:`~contextvars.ContextVar` rather than on the request object so
that service and model layers can reach it without every function signature having
to thread a tenant argument through.
"""

from contextlib import contextmanager
from contextvars import ContextVar

_current_tenant_id: ContextVar[int | None] = ContextVar("current_tenant_id", default=None)


def set_current_tenant_id(tenant_id: int | None) -> None:
    """Set the tenant for the current context."""
    _current_tenant_id.set(tenant_id)


def current_tenant_id() -> int | None:
    """Return the tenant for the current context, or ``None`` if unset."""
    return _current_tenant_id.get()


def clear_current_tenant() -> None:
    """Clear the tenant. Called when a request finishes."""
    _current_tenant_id.set(None)


@contextmanager
def tenant_context(tenant_id: int | None):
    """Temporarily run inside a tenant's context.

    Used by management commands and tests, which have no middleware to set it.

    Args:
        tenant_id: The tenant to activate.
    """
    token = _current_tenant_id.set(tenant_id)
    try:
        yield
    finally:
        _current_tenant_id.reset(token)
