"""Probes that make a latency guarantee checkable by cause rather than by clock.

Re-exported here so call sites read ``from agentdesk.obs import model_span`` rather than
reaching two packages deep for what is a single, small idea.
"""

from agentdesk.obs.probes import (
    DB_ACQUIRE,
    DB_RELEASE,
    MODEL_END,
    MODEL_START,
    TOOL_CALL,
    Event,
    Trace,
    connections_held_across_model_calls,
    db_span,
    model_call_threads,
    model_span,
    record,
    tracing,
)

__all__ = [
    "DB_ACQUIRE",
    "DB_RELEASE",
    "MODEL_END",
    "MODEL_START",
    "TOOL_CALL",
    "Event",
    "Trace",
    "connections_held_across_model_calls",
    "db_span",
    "model_call_threads",
    "model_span",
    "record",
    "tracing",
]
