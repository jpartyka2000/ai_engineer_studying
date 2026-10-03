"""The agent loop.

Every test here is about **progress**: whether the loop advances, whether it stops, and
whether the model can tell that its request was answered. None of them need a database --
the tools are deterministic stand-ins, but the registry, prompt, keying and loop are the
shipping code.
"""

from __future__ import annotations

import pytest

from agentdesk.assistant.loop import StepBudgetExceeded, run_agent
from agentdesk.assistant.recording import Script, ScriptedCall
from agentdesk.llm.recorded_client import CassetteMissError, RunawayLoopError


def test_a_two_tool_question_is_answered(registry, recorder, two_step) -> None:
    client = recorder(two_step)
    run = run_agent(two_step.question, registry=registry, client=client, max_steps=6)

    assert run.answer == two_step.answer
    assert run.tools_used == ("fact", "echo")
    assert all(step.ok for step in run.steps)


def test_each_observation_reaches_the_model(registry, recorder, two_step) -> None:
    """**The property ex-052 turns on, stated directly.**

    The second decision is recorded against a conversation that has seen the first tool's
    output. If that output does not arrive as a ``tool`` message, the model is asked the
    same question it was asked before -- so it repeats itself, and the run never advances
    past the first tool.
    """
    client = recorder(two_step)
    run = run_agent(two_step.question, registry=registry, client=client, max_steps=6)

    tool_messages = [message for message in run.messages if message.role == "tool"]
    assert len(tool_messages) == 2
    assert [message.name for message in tool_messages] == ["fact", "echo"]
    assert all(message.tool_call_id for message in tool_messages), (
        "a tool result must name the call it answers"
    )
    assert len(set(run.tools_used)) == len(run.tools_used), (
        "a tool was called twice: its first result did not reach the model"
    )


def test_a_tool_result_is_matched_to_its_call(registry, recorder, two_step) -> None:
    client = recorder(two_step)
    run = run_agent(two_step.question, registry=registry, client=client, max_steps=6)

    requested = [
        call.id
        for message in run.messages
        if message.role == "assistant"
        for call in message.tool_calls
    ]
    answered = [m.tool_call_id for m in run.messages if m.role == "tool"]
    assert requested == answered


def test_a_failing_tool_becomes_an_observation_not_an_exception(
    registry, recorder
) -> None:
    """The model has to be able to read its own mistake to correct it."""
    script = Script(
        id="recovers",
        question="What is the probation period?",
        calls=(
            ScriptedCall(tool="fact", arguments={"topic": "probation"}, call_id="c0"),
        ),
        answer="Probation is three months.",
    )
    bad = Script(
        id="recovers-after-error",
        question="What is the notice period?",
        calls=(
            ScriptedCall(tool="fact", arguments={"topic": "notice"}, call_id="c0"),
            ScriptedCall(tool="fact", arguments={"topic": "probation"}, call_id="c1"),
        ),
        answer="There is no recorded notice period; probation is three months.",
    )
    client = recorder(script, bad)

    run = run_agent(bad.question, registry=registry, client=client, max_steps=6)
    assert run.steps[0].ok is False
    assert "error:" in run.steps[0].observation
    assert run.steps[1].ok is True
    assert run.answer == bad.answer


def test_the_budget_counts_rounds_not_successes(registry, recorder) -> None:
    """**The property ex-051 turns on, stated directly.**

    Every call in this script fails. A budget that only counts *useful* rounds never
    counts at all here, and the loop runs until something else stops it -- in production,
    nothing does.
    """
    script = Script(
        id="all-failures",
        question="What is the mileage rate?",
        calls=tuple(
            ScriptedCall(tool="fact", arguments={"topic": f"mileage-{i}"}, call_id=f"c{i}")
            for i in range(8)
        ),
        answer="never reached",
    )
    client = recorder(script)

    with pytest.raises(StepBudgetExceeded) as caught:
        run_agent(script.question, registry=registry, client=client, max_steps=3)

    assert "3 steps" in str(caught.value)


def test_the_budget_is_reached_even_when_every_tool_succeeds(registry, recorder) -> None:
    """The same ceiling, on the path where nothing is going wrong at all."""
    script = Script(
        id="endless",
        question="Count everything.",
        calls=tuple(
            ScriptedCall(tool="count", arguments={"n": i}, call_id=f"c{i}")
            for i in range(8)
        ),
        answer="never reached",
    )
    client = recorder(script)

    with pytest.raises(StepBudgetExceeded):
        run_agent(script.question, registry=registry, client=client, max_steps=4)


def test_the_client_refuses_an_unbounded_conversation(registry, recorder) -> None:
    """The second circuit breaker, independent of the loop's own budget.

    Proves the guard fires rather than merely existing: a loop with no ceiling at all
    still terminates, with an error that names the cause, instead of hanging CI.
    """
    script = Script(
        id="endless",
        question="Count everything.",
        calls=tuple(
            ScriptedCall(tool="count", arguments={"n": i}, call_id=f"c{i}")
            for i in range(12)
        ),
        answer="never reached",
    )
    client = recorder(script, max_observations=4)

    with pytest.raises(RunawayLoopError, match="still not stopping"):
        run_agent(script.question, registry=registry, client=client, max_steps=50)


def test_the_client_refuses_to_serve_one_state_forever(registry, recorder, two_step) -> None:
    """The other circuit breaker: an agent stuck, rather than an agent running on."""
    client = recorder(two_step, runaway_limit=3)
    messages = []
    from agentdesk.assistant import prompt
    from agentdesk.llm.recorded_client import tools_digest

    messages = prompt.build_conversation(registry, two_step.question)
    digest = tools_digest(registry.specs())
    for _ in range(3):
        client.decide(messages=messages, tools=digest)

    with pytest.raises(RunawayLoopError, match="served"):
        client.decide(messages=messages, tools=digest)


def test_a_zero_step_budget_is_rejected(registry, recorder, two_step) -> None:
    client = recorder(two_step)
    with pytest.raises(ValueError, match="at least one step"):
        run_agent(two_step.question, registry=registry, client=client, max_steps=0)


def test_an_unrecorded_question_raises_rather_than_inventing(
    registry, recorder, two_step
) -> None:
    client = recorder(two_step)
    with pytest.raises(CassetteMissError):
        run_agent("something nobody recorded", registry=registry, client=client)


def test_the_run_serializes(registry, recorder, two_step) -> None:
    client = recorder(two_step)
    payload = run_agent(
        two_step.question, registry=registry, client=client, max_steps=6
    ).as_dict()

    assert payload["answer"] == two_step.answer
    assert [step["tool"] for step in payload["steps"]] == ["fact", "echo"]
    assert payload["citations"] == ["refund"]
