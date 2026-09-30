"""Host port allocation for exercise containers.

Every exercise publishes its database on a host port so the user can point their own
``psql``, GUI client, or browser at it. Those ports must avoid three things: the
study app's own services (Postgres on 5432, Redis on 6379, runserver on 8000),
anything else already listening, and ports handed to another workspace that has not
bound them yet.

Only the *published* port moves. Inside the exercise's compose network services
still talk to ``db:5432``, so the exercise's own configuration stays exactly as
realistic as it would be in production.
"""

from __future__ import annotations

import logging
import socket
from typing import Final

from django.conf import settings

from apps.workspace.exceptions import PortAllocationError

logger = logging.getLogger(__name__)

#: Give up rather than scanning the whole range forever.
MAX_PROBES: Final[int] = 400


def reserved_ports() -> set[int]:
    """Return ports that must never be handed to an exercise."""
    return set(settings.WORKSPACE_RESERVED_PORTS)


def ports_held_by_live_sessions() -> set[int]:
    """Return every host port recorded against a session that is still active.

    Probing alone is not enough: a workspace can be scaffolded minutes before its
    containers bind, and two exercises prepared back to back would otherwise be
    offered the same free port.
    """
    # Imported here to keep this module importable without the app registry, which
    # matters for the unit tests that exercise probing in isolation.
    from apps.workspace.models import WorkspaceSession

    held: set[int] = set()
    rows = WorkspaceSession.objects.filter(status__in=WorkspaceSession.ACTIVE_STATUSES).values_list(
        "host_ports", flat=True
    )
    for mapping in rows:
        if not isinstance(mapping, dict):
            continue
        for value in mapping.values():
            try:
                held.add(int(value))
            except (TypeError, ValueError):
                continue
    return held


def is_port_free(port: int, host: str = "127.0.0.1") -> bool:
    """Check whether a TCP port can be bound right now.

    ``SO_REUSEADDR`` is deliberately **not** set: with it, binding can succeed on a
    port that is in ``TIME_WAIT`` or already bound by another socket with the option
    set, which would report a busy port as free.

    Args:
        port: The port to test.
        host: The interface to test on.

    Returns:
        Whether the port is bindable.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def allocate(services: list[str], *, exclude: set[int] | None = None) -> dict[str, int]:
    """Allocate one free host port per service.

    Args:
        services: Service names needing a published port, e.g.
            ``["postgres", "mongodb"]``.
        exclude: Extra ports to avoid, beyond the reserved set and ports held by
            live sessions.

    Returns:
        Mapping of service name to allocated host port.

    Raises:
        PortAllocationError: If the configured range cannot satisfy the request.
    """
    if not services:
        return {}

    low, high = settings.WORKSPACE_PORT_RANGE
    blocked = reserved_ports() | ports_held_by_live_sessions() | set(exclude or set())

    allocated: dict[str, int] = {}
    candidate = low
    probes = 0

    for service in services:
        while True:
            if candidate > high or probes >= MAX_PROBES:
                raise PortAllocationError(
                    f"No free host port for {service!r} in range {low}-{high} "
                    f"after {probes} probes; {len(blocked)} ports are unavailable"
                )
            probes += 1
            port = candidate
            candidate += 1
            if port in blocked:
                continue
            if not is_port_free(port):
                blocked.add(port)
                continue
            allocated[service] = port
            # Reserve within this call too, so two services never collide.
            blocked.add(port)
            break

    logger.debug("allocated host ports %s", allocated)
    return allocated


def env_var_for(service: str) -> str:
    """Return the ``.env`` variable name a compose file reads for a service's port.

    Args:
        service: A service name such as ``"postgres"``.

    Returns:
        The variable name, e.g. ``"WS_POSTGRES_PORT"``.
    """
    return f"WS_{service.upper()}_PORT"
