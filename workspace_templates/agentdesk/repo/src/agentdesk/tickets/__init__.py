"""The support desk: tickets, SLA timers, search.

The original product, and the part that must keep working when the assistant does not.
Nothing in this package imports :mod:`agentdesk.assistant`; ``tests/test_layering.py``
enforces that, because an import is all it takes for a model outage to become a desk
outage.
"""

from agentdesk.tickets.models import Priority, Status, Ticket

__all__ = ["Priority", "Status", "Ticket"]
