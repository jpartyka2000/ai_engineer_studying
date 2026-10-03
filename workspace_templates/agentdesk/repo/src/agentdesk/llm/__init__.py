"""The model layer: conversation types and the recorded client.

There is no live API call in this package or anywhere downstream of it. The client reads
``fixtures/llm_cassettes/``; a miss raises. :mod:`agentdesk.llm.recorded_client` explains
what the cassette key covers and -- more importantly -- what it deliberately leaves out.
"""

from agentdesk.llm.recorded_client import (
    CASSETTE_VERSION,
    MAX_OBSERVATIONS,
    RUNAWAY_LIMIT,
    CassetteMissError,
    RecordedClient,
    RunawayLoopError,
    cassette_key,
    context_digest,
    observations_digest,
    tools_digest,
)
from agentdesk.llm.types import Decision, Message, ToolCall

__all__ = [
    "CASSETTE_VERSION",
    "MAX_OBSERVATIONS",
    "RUNAWAY_LIMIT",
    "CassetteMissError",
    "Decision",
    "Message",
    "RecordedClient",
    "RunawayLoopError",
    "ToolCall",
    "cassette_key",
    "context_digest",
    "observations_digest",
    "tools_digest",
]
