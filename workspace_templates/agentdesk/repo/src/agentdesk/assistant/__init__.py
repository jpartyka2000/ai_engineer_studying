"""The assistant: tools, the prompt built from them, and the loop that runs them.

Depends on :mod:`agentdesk.tickets`; the reverse import does not exist and
``tests/test_layering.py`` keeps it that way. The desk predates this package by three
years and has to keep serving when it is down.
"""

from agentdesk.assistant.loop import Run, Step, StepBudgetExceeded, run_agent
from agentdesk.assistant.registry import (
    InvalidArguments,
    Param,
    Registry,
    ToolError,
    ToolSpec,
    UnknownTool,
)
from agentdesk.assistant.tools import build_registry

__all__ = [
    "InvalidArguments",
    "Param",
    "Registry",
    "Run",
    "Step",
    "StepBudgetExceeded",
    "ToolError",
    "ToolSpec",
    "UnknownTool",
    "build_registry",
    "run_agent",
]
