"""Turning an intended conversation into cassettes.

A recording is written as a **script**: the tools the model should ask for, in order, and
the answer it should end on. This module replays that script against the real registry,
computes the key at each point the model would have been consulted, and writes one
cassette per point.

**Why replay rather than hand-write the keys.** A key depends on the observations, and an
observation is whatever the tool actually returned -- which depends on the seeded data, the
clock, and the tool's own formatting. Hand-computing that is error-prone in a way that
fails silently: a key that is wrong by one character produces a cassette nobody will ever
read, and the suite reports a miss somewhere else entirely.

Replaying means the recording and the runtime agree by construction, because they are the
same code path. ``tests/test_cassette_consistency.py`` then checks the other direction:
that every cassette on disk is reachable from some script, so a stale one cannot sit there
pretending to be coverage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from agentdesk.assistant import prompt
from agentdesk.assistant.registry import (
    InvalidArguments,
    Registry,
    ToolError,
    UnknownTool,
)
from agentdesk.llm.recorded_client import (
    CASSETTE_VERSION,
    cassette_key,
    context_digest,
    observations_digest,
    tools_digest,
)
from agentdesk.llm.types import Message, ToolCall


@dataclass(frozen=True)
class ScriptedCall:
    """One tool call the model should make.

    Attributes:
        tool: Registered tool name.
        arguments: Arguments to pass. Recorded verbatim, including deliberately bad ones
            -- a recording of the model getting an argument wrong is how the recovery
            path gets tested at all.
        call_id: Correlation id. Stable per position so re-recording does not churn.
    """

    tool: str
    arguments: dict
    call_id: str = ""


@dataclass(frozen=True)
class Script:
    """One intended conversation.

    Attributes:
        id: Short handle, used in filenames and error messages.
        question: What the support agent asks.
        ticket_body: Customer text this concerns, if any. Fenced before use.
        calls: Tool calls in order, one per round.
        answer: The final reply.
        citations: What the answer leans on.
        notes: Why this recording exists. Written into every cassette it produces, so a
            cassette found in isolation still explains itself.
    """

    id: str
    question: str
    calls: tuple[ScriptedCall, ...]
    answer: str
    citations: tuple[str, ...] = ()
    ticket_body: str | None = None
    notes: str = ""

    @classmethod
    def from_dict(cls, payload: dict) -> "Script":
        """Build a script from one line of ``fixtures/recordings.jsonl``."""
        return cls(
            id=payload["id"],
            question=payload["question"],
            calls=tuple(
                ScriptedCall(
                    tool=call["tool"],
                    arguments=call.get("arguments", {}),
                    call_id=call.get("call_id", f"{payload['id']}-{index}"),
                )
                for index, call in enumerate(payload.get("calls", ()))
            ),
            answer=payload["answer"],
            citations=tuple(payload.get("citations", ())),
            ticket_body=payload.get("ticket_body"),
            notes=payload.get("notes", ""),
        )


def load_scripts(path: Path) -> list[Script]:
    """Read every script from a JSONL transcript."""
    scripts = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            scripts.append(Script.from_dict(json.loads(line)))
    return scripts


def record(
    script: Script,
    *,
    registry: Registry,
    model: str,
    cassette_dir: Path,
) -> list[str]:
    """Write the cassettes for one script.

    Replays the conversation exactly as :func:`~agentdesk.assistant.loop.run_agent` would:
    build the opening messages, and at each round compute the key, write what the model
    should say, then run the tool and append its result the way the loop does.

    Args:
        script: The intended conversation.
        registry: The real tool registry. Tools **are executed** -- their output is what
            the key is built from.
        model: Model identifier.
        cassette_dir: Where to write.

    Returns:
        The keys written, in order.
    """
    cassette_dir.mkdir(parents=True, exist_ok=True)
    digest = tools_digest(registry.specs())
    messages = prompt.build_conversation(
        registry, script.question, ticket_body=script.ticket_body
    )
    written: list[str] = []

    for index, call in enumerate(script.calls):
        key = _write(
            cassette_dir,
            model=model,
            digest=digest,
            messages=messages,
            question=script.question,
            context=script.ticket_body,
            payload={
                "tool_calls": [
                    {
                        "id": call.call_id,
                        "name": call.tool,
                        "arguments": call.arguments,
                    }
                ]
            },
            script=script,
            position=index,
        )
        written.append(key)

        tool_call = ToolCall(id=call.call_id, name=call.tool, arguments=call.arguments)
        observation = _invoke(registry, tool_call)
        messages.append(Message(role="assistant", tool_calls=(tool_call,)))
        messages.append(
            Message(
                role="tool",
                content=observation,
                tool_call_id=call.call_id,
                name=call.tool,
            )
        )

    key = _write(
        cassette_dir,
        model=model,
        digest=digest,
        messages=messages,
        question=script.question,
        context=script.ticket_body,
        payload={"text": script.answer, "citations": list(script.citations)},
        script=script,
        position=len(script.calls),
    )
    written.append(key)
    return written


def _invoke(registry: Registry, call: ToolCall) -> str:
    """Run a tool the way the loop does, including turning its failures into text."""
    try:
        return registry.invoke(call)
    except (UnknownTool, InvalidArguments, ToolError) as exc:
        return f"error: {exc}"


def _write(
    cassette_dir: Path,
    *,
    model: str,
    digest: str,
    messages: list[Message],
    question: str,
    context: str | None,
    payload: dict,
    script: Script,
    position: int,
) -> str:
    """Write one cassette and return its key."""
    key = cassette_key(
        model=model,
        tools=digest,
        observations=observations_digest(messages),
        user_message=question,
        context=context_digest(context),
    )
    body = {
        "version": CASSETTE_VERSION,
        "script": script.id,
        "position": position,
        "question": question,
        "notes": script.notes,
        **payload,
    }
    (cassette_dir / f"{key}.json").write_text(
        json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return key
