"""The conversation types, shared by the prompt layer, the loop and the recorded client.

Kept in their own module because all three depend on them and none should depend on each
other: the prompt layer builds messages, the loop appends them, the client reads them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class ToolCall:
    """A model's request to run one tool.

    Attributes:
        id: Correlates this call with the message carrying its result. The model may ask
            for several tools before any has answered, and without an id there is no way
            to say which result belongs to which call.
        name: Registered tool name.
        arguments: Arguments as the model supplied them -- **unvalidated**. Validating
            them is :mod:`agentdesk.assistant.registry`'s job and happens at the boundary,
            not here.
    """

    id: str
    name: str
    arguments: dict

    def canonical(self) -> str:
        """Return a stable string form, used in cassette keys.

        Keys are sorted so that two identical calls built in different orders hash the
        same. Without that, a dict literal reordered during a refactor would invalidate
        every recording.
        """
        return json.dumps(
            {"name": self.name, "arguments": self.arguments},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )


@dataclass(frozen=True)
class Message:
    """One turn of the conversation.

    Attributes:
        role: Who is speaking.
        content: Text content.
        tool_calls: On an ``assistant`` message, the tools it asked for.
        tool_call_id: On a ``tool`` message, which call this answers.
        name: On a ``tool`` message, which tool produced it.

        **The role of a tool result is load-bearing, not cosmetic.** A result pasted into
        an ``assistant`` or ``user`` message is not a tool result -- it is prose that
        happens to contain the same characters. The model has no way to tell that its
        request was honoured, so it asks again, and the loop goes round.
    """

    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)
    tool_call_id: str | None = None
    name: str | None = None

    def __post_init__(self) -> None:
        if self.role == "tool" and self.tool_call_id is None:
            raise ValueError("a tool message must name the call it answers")
        if self.tool_calls and self.role != "assistant":
            raise ValueError("only an assistant message may request tools")

    def as_dict(self) -> dict:
        """Return the wire form, omitting fields that do not apply to this role."""
        payload: dict = {"role": self.role, "content": self.content}
        if self.tool_calls:
            payload["tool_calls"] = [
                {"id": c.id, "name": c.name, "arguments": c.arguments}
                for c in self.tool_calls
            ]
        if self.tool_call_id is not None:
            payload["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            payload["name"] = self.name
        return payload


@dataclass(frozen=True)
class Decision:
    """What the model decided to do next.

    Exactly one of the two shapes: ask for tools, or answer. A response carrying both is
    a protocol error and :meth:`__post_init__` rejects it rather than letting the loop
    guess which half to honour.

    Attributes:
        tool_calls: Tools to run, if any.
        text: The answer, when there are no tool calls.
        citations: Ticket ids and article slugs the answer leans on.
    """

    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)
    text: str = ""
    citations: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.tool_calls and self.text:
            raise ValueError("a decision either calls tools or answers, not both")

    @property
    def is_final(self) -> bool:
        """Whether this decision ends the run."""
        return not self.tool_calls
