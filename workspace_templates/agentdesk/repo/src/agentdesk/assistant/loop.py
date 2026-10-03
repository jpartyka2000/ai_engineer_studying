"""The agent loop.

Ask the model what to do, do it, show it the result, repeat until it answers.

**The two things this loop has to get right**, both of which look like bookkeeping and
are not:

*The budget must count every round, not every useful round.* The tempting version
increments only when a tool succeeded, on the reasoning that a failed call "didn't really
do anything". It did: it cost a model call, and it is exactly the situation that repeats.
A tool erroring on bad arguments produces a model that tries again, which errors again --
and a budget that only counts successes never counts at all. The loop that runs forever is
always the one that was sure it was making progress.

*A tool result must be appended as a tool result.* The role carries the meaning. The same
characters in an assistant message are the model's own words quoted back at it, and in a
user message they are something the human said; in neither case has the model's request
been answered, so it asks again. See :mod:`agentdesk.llm.types` for why this is checked
rather than assumed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from agentdesk.assistant import prompt
from agentdesk.assistant.registry import (
    InvalidArguments,
    Registry,
    ToolError,
    UnknownTool,
)
from agentdesk.config import SETTINGS
from agentdesk.llm.recorded_client import RecordedClient, tools_digest
from agentdesk.llm.types import Message, ToolCall
from agentdesk.obs import TOOL_CALL, record

logger = logging.getLogger(__name__)


class StepBudgetExceeded(RuntimeError):
    """Raised when an agent run hits its ceiling without reaching an answer.

    A normal operational outcome, not a crash: some questions genuinely cannot be
    answered with the available tools, and the model will keep looking until told to
    stop. The caller turns this into "I could not work that out" for the user.
    """


@dataclass(frozen=True)
class Step:
    """One tool call and what came back.

    Attributes:
        index: Zero-based position in the run.
        call: What the model asked for.
        observation: What the tool returned, or the error text if it failed. Either way
            this is what the model is shown -- an error it can read is how it recovers.
        ok: Whether the tool succeeded.
    """

    index: int
    call: ToolCall
    observation: str
    ok: bool


@dataclass(frozen=True)
class Run:
    """The result of one agent run.

    Attributes:
        question: What was asked.
        answer: The drafted reply.
        citations: Ticket ids and article slugs the answer leans on.
        steps: Every tool call made, in order.
        messages: The full conversation, for debugging and for the API's trace view.
    """

    question: str
    answer: str
    citations: tuple[str, ...] = field(default_factory=tuple)
    steps: tuple[Step, ...] = field(default_factory=tuple)
    messages: tuple[Message, ...] = field(default_factory=tuple)

    @property
    def tools_used(self) -> tuple[str, ...]:
        """Tool names in call order, duplicates included.

        Duplicates are the interesting part: the same tool with the same arguments twice
        in one run means the first result did not reach the model.
        """
        return tuple(step.call.name for step in self.steps)

    def as_dict(self) -> dict:
        """Return a JSON-serializable view."""
        return {
            "question": self.question,
            "answer": self.answer,
            "citations": list(self.citations),
            "steps": [
                {
                    "index": step.index,
                    "tool": step.call.name,
                    "arguments": step.call.arguments,
                    "observation": step.observation,
                    "ok": step.ok,
                }
                for step in self.steps
            ],
        }


def run_agent(
    question: str,
    *,
    registry: Registry,
    client: RecordedClient,
    ticket_body: str | None = None,
    max_steps: int | None = None,
) -> Run:
    """Run the agent until it answers or runs out of steps.

    Args:
        question: The support agent's question.
        registry: Tools the model may call.
        client: The model.
        ticket_body: Customer text this question concerns. Fenced before it reaches the
            prompt; see :func:`agentdesk.assistant.prompt.fence`.
        max_steps: Ceiling on tool-calling rounds. Defaults to the configured value.

    Returns:
        The completed :class:`Run`.

    Raises:
        StepBudgetExceeded: If the ceiling is reached with no answer.
    """
    ceiling = SETTINGS.max_agent_steps if max_steps is None else max_steps
    if ceiling < 1:
        raise ValueError("an agent needs at least one step")

    messages = prompt.build_conversation(registry, question, ticket_body=ticket_body)
    digest = tools_digest(registry.specs())
    steps: list[Step] = []

    # Counts rounds, not successes. Every pass through this loop spends a model call,
    # which is the resource the budget exists to bound.
    for _ in range(ceiling):
        decision = client.decide(messages=messages, tools=digest, context=ticket_body)

        if decision.is_final:
            messages.append(Message(role="assistant", content=decision.text))
            return Run(
                question=question,
                answer=decision.text,
                citations=decision.citations,
                steps=tuple(steps),
                messages=tuple(messages),
            )

        messages.append(Message(role="assistant", tool_calls=decision.tool_calls))
        for call in decision.tool_calls:
            observation, ok = _invoke(registry, call)
            record(TOOL_CALL, tool=call.name, ok=ok)
            steps.append(
                Step(index=len(steps), call=call, observation=observation, ok=ok)
            )
            # role="tool", with the id of the call it answers. Both halves are required
            # for the model to count this as its request having been served.
            messages.append(
                Message(
                    role="tool",
                    content=observation,
                    tool_call_id=call.id,
                    name=call.name,
                )
            )

    raise StepBudgetExceeded(
        f"{ceiling} steps without an answer; tools called: "
        f"{', '.join(step.call.name for step in steps) or 'none'}"
    )


def _invoke(registry: Registry, call: ToolCall) -> tuple[str, bool]:
    """Run one tool call, turning every expected failure into a readable observation.

    The three caught exceptions are the ones the model can do something about: a tool that
    does not exist, arguments that do not fit, and a tool that ran and failed. Each comes
    back as text so the model can correct itself on the next round.

    Anything else propagates. A ``KeyError`` from inside a handler is a bug in our code,
    and feeding it to the model as an observation would bury it.
    """
    try:
        return registry.invoke(call), True
    except (UnknownTool, InvalidArguments, ToolError) as exc:
        logger.info("tool %s failed: %s", call.name, exc)
        return f"error: {exc}", False
