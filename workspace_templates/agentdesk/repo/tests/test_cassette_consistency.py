"""The join between the transcript, the cassettes and the runtime.

Three artifacts have to agree: ``fixtures/recordings.jsonl`` says what should happen,
``fixtures/llm_cassettes/`` holds the keyed responses, and the loop computes keys at run
time. Any two of them can agree while the third drifts, and the symptom is always the
same unhelpful thing -- a cassette miss in a test that looks unrelated.

So this file checks the join in **both directions**: every script is replayable, and
every cassette on disk belongs to some script. The second direction is the one that
matters for rot. A stale cassette is invisible -- it sits there looking like coverage,
and the conversation it was recorded for no longer exists.

Marked ``db`` because the tools read the seeded database, and their output is what the
keys are built from. That coupling is the design, not an accident: a recording that did
not run the real tools would not prove the real tools still return what was recorded.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentdesk.assistant.loop import run_agent
from agentdesk.assistant.recording import load_scripts
from agentdesk.assistant.service import build_client
from agentdesk.assistant.tools import build_registry
from agentdesk.config import SETTINGS
from agentdesk.llm.recorded_client import CASSETTE_VERSION

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def scripts():
    return load_scripts(SETTINGS.fixtures_dir / "recordings.jsonl")


@pytest.fixture(scope="module")
def cassette_paths() -> list[Path]:
    return sorted(SETTINGS.cassette_dir.glob("*.json"))


def test_there_are_cassettes_at_all(cassette_paths: list[Path]) -> None:
    """Guards every other test in this file.

    Without it, an empty fixture directory would make the "no orphans" check pass
    trivially and the suite would report health on a repository with no recordings.
    """
    assert len(cassette_paths) > 20


def test_every_script_replays(scripts) -> None:
    """The forward direction: what the transcript says should happen, happens."""
    registry = build_registry()
    for script in scripts:
        client = build_client()
        run = run_agent(
            script.question,
            registry=registry,
            client=client,
            ticket_body=script.ticket_body,
            max_steps=len(script.calls) + 1,
        )
        assert run.answer == script.answer, f"{script.id} ended somewhere else"
        assert run.tools_used == tuple(call.tool for call in script.calls), (
            f"{script.id} called a different sequence of tools"
        )


def test_every_cassette_belongs_to_a_script(cassette_paths: list[Path], scripts) -> None:
    """The reverse direction, and the one that catches rot.

    A cassette whose script has been deleted or rewritten is not harmless clutter: it is
    a recording of a conversation that can no longer occur, taking up space in a
    directory people treat as evidence of coverage.
    """
    known = {script.id for script in scripts}
    orphans = []
    for path in cassette_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("script") not in known:
            orphans.append((path.name[:12], payload.get("script")))
    assert orphans == [], f"cassettes with no script: {orphans}"


def test_the_count_matches_the_transcript(cassette_paths: list[Path], scripts) -> None:
    """One cassette per decision point: one per tool call, plus one for the answer."""
    expected = sum(len(script.calls) + 1 for script in scripts)
    assert len(cassette_paths) == expected


def test_every_cassette_is_the_current_version(cassette_paths: list[Path]) -> None:
    for path in cassette_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["version"] == CASSETTE_VERSION, f"{path.name} is stale"


def test_every_cassette_explains_itself(cassette_paths: list[Path]) -> None:
    """A cassette found in isolation has to say what it is for.

    These are opaque hex filenames. Without the script id, the position and the note, a
    failing key is a dead end -- you cannot grep for it and you cannot tell which
    conversation it belonged to.
    """
    for path in cassette_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload.get("script"), f"{path.name} has no script id"
        assert payload.get("question"), f"{path.name} has no question"
        assert "position" in payload, f"{path.name} has no position"


def test_a_decision_either_calls_tools_or_answers(cassette_paths: list[Path]) -> None:
    """Both at once is a protocol error the loop would have to guess its way through."""
    for path in cassette_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        has_calls = bool(payload.get("tool_calls"))
        has_text = bool(payload.get("text"))
        assert has_calls != has_text, f"{path.name} does both or neither"


def test_every_recorded_tool_is_registered(cassette_paths: list[Path]) -> None:
    """A recording that names a tool nobody registered can only fail at run time."""
    registered = {spec.name for spec in build_registry().specs()}
    for path in cassette_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for call in payload.get("tool_calls", ()):
            assert call["name"] in registered, f"{path.name} calls unknown {call['name']}"


def test_the_transcript_covers_the_shapes_the_suite_needs(scripts) -> None:
    """The corpus is designed, not collected, so assert the design holds.

    Each clause here corresponds to a path that is otherwise untested: a multi-step
    conversation, a recovery from a bad argument, and a run that must search before it
    knows what to fetch.
    """
    lengths = {len(script.calls) for script in scripts}
    assert max(lengths) >= 3, "no conversation is long enough to show ordering"
    assert 0 in lengths, "nothing covers answering with no tools"

    arguments = [
        call.arguments
        for script in scripts
        for call in script.calls
    ]
    assert any(
        isinstance(argument.get("ticket_id"), str) for argument in arguments
    ), "nothing records the model getting an argument type wrong"

    assert any(
        script.calls and script.calls[0].tool == "search_tickets" for script in scripts
    ), "nothing records searching before fetching"
