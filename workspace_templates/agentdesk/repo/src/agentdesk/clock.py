"""The clock, in one place and overridable.

**Why a module instead of calling** :func:`datetime.now` **where it is needed.**

Two reasons, and the second is the one that forced it.

*SLA state is a function of now.* Every test about breaches would otherwise need either a
sleep or a patch of a different symbol in each module, and both are how time-dependent
test suites become flaky suites.

*Tool output feeds cassette keys.* ``lookup_ticket`` reports whether a ticket has breached
its SLA. That text becomes an observation, the observation becomes part of the cassette
key, and a key that depends on the wall clock is a key that is different tomorrow -- so
every recorded conversation would expire overnight. Pinning the clock in CI and in the
exercise container is what makes the recordings reproducible at all.

Set ``AGENTDESK_NOW`` to an ISO-8601 instant to pin it. Production sets nothing and gets
the real clock.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

#: The instant CI and the exercise container pin to. Chosen to sit a few days after the
#: newest seeded ticket, so the queue has a realistic mix of fresh, at-risk and breached
#: work rather than being uniformly one or the other.
PINNED = "2025-06-18T09:00:00+00:00"


def now() -> datetime:
    """Return the current instant, UTC.

    Returns:
        ``AGENTDESK_NOW`` if set, otherwise the real clock. Always timezone-aware.

    Raises:
        ValueError: If ``AGENTDESK_NOW`` is set to something unparseable. Deliberately
            loud: silently falling back to the real clock would turn a typo into a
            suite that fails somewhere else entirely, tomorrow.
    """
    override = os.environ.get("AGENTDESK_NOW")
    if not override:
        return datetime.now(timezone.utc)

    instant = datetime.fromisoformat(override)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(timezone.utc)


def is_pinned() -> bool:
    """Return whether the clock is currently overridden."""
    return bool(os.environ.get("AGENTDESK_NOW"))
