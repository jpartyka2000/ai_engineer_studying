"""Exercises built on the ``agentdesk`` base application.

Same ``(base_app, mutations)`` shape as the other catalog modules, and baselines are
likewise **measured** into ``baselines.json`` by the verification harness rather than
authored here.

What this base app adds to the catalog is an agent that **acts**. Everywhere else the
model answers a question; here it chooses a tool, reads what came back, and chooses
again. That loop has its own failure modes, and they do not look like the retrieval
failures in ``ragqa``: the assistant does not answer the wrong thing, it fails to stop,
or asks the same question twice, or acts on an argument it made up.

The other half of the app is the **cost of having an assistant at all**. ``agentdesk`` is
a support desk that existed for three years before anyone added AI to it, and three of
these exercises are about the assistant degrading the product around it -- a drained
connection pool, a blocked event loop, a page that makes one model call per row. Those
briefs are reported by people who do not use the assistant and do not know it exists,
which is exactly how they arrive in real life.

**The two serving exercises contain no GPU and no inference**, and the briefs say so.
``src/agentdesk/serving/`` is the control plane: VRAM arithmetic, a paged KV allocator
and an admission policy, in exact integer arithmetic. That is where production OOMs are
actually caused -- the card did what it was told and was told wrong -- and it is the part
an interviewer probes. What it will not teach is any CUDA API.
"""

import json
from pathlib import Path
from typing import Any

from apps.workspace.enums import BaseApp, CheckKind, Database, Difficulty, ExerciseType

_BASELINES: dict[str, dict[str, Any]] = json.loads(
    (Path(__file__).parent / "baselines.json").read_text(encoding="utf-8")
)


def baseline(slug: str) -> dict[str, Any]:
    """Return the measured pre-fix baseline for an exercise.

    Args:
        slug: The exercise slug.

    Returns:
        A dict with ``failing_nodes``, ``passing_nodes`` and ``metrics``.

    Raises:
        KeyError: If no baseline has been measured, which should fail the seed command
            rather than silently ship an ungradeable exercise.
    """
    data = _BASELINES[slug]
    return {
        "failing_nodes": data["failing_nodes"],
        "passing_nodes": data["passing_nodes"],
        "metrics": data.get("metrics", {}),
    }


#: The tests are the proof, so editing them is tampering. Three additions specific to
#: this base app: ``fixtures/**`` because the recordings are what make an agent run
#: reproducible at all, ``tools/**`` because those scripts regenerate the fixtures, and
#: ``db/migrations/**`` because the harness applies migrations once before both grading
#: phases -- a schema change could not be undone between them even if it were the right
#: fix, and none of these exercises needs one.
STANDARD_PROTECTED = [
    "tests/**",
    "pyproject.toml",
    "ci/run_ci.sh",
    ".github/workflows/ci.yml",
    "fixtures/**",
    "tools/gen_fixtures.py",
    "tools/gen_recordings.py",
    "db/migrations/**",
]

#: Shared context: what the cassette key covers, and what it deliberately does not.
RECORDED_MODEL_EXCERPT = {
    "path": "src/agentdesk/llm/recorded_client.py",
    "line_range": "1-46",
    "why": (
        "The cassette key, part by part. The observations digest is the half that makes "
        "a loop recordable -- progress *is* the key moving -- and the assembled prompt "
        "is deliberately absent so that rewording an instruction does not invalidate "
        "every recording. Read before changing anything about the loop or the tools."
    ),
}

#: Shared context: why latency is asserted as mechanism rather than measured.
MECHANISM_NOT_CLOCK_EXCERPT = {
    "path": "src/agentdesk/obs/probes.py",
    "line_range": "1-30",
    "why": (
        "'Why this module exists instead of a benchmark'. The p95 test that used to live "
        "here was deleted; this records what replaced it and why a threshold sends you "
        "to a profiler while a mechanism sends you to a line."
    ),
}

#: Shared context: where the bytes go on a served model.
VRAM_EXCERPT = {
    "path": "src/agentdesk/serving/memory.py",
    "line_range": "1-40",
    "why": (
        "What this layer is and is not -- planning, not inference, no accelerator "
        "anywhere. Then the three claims on the budget in ascending order of how often "
        "they are forgotten, and the KV formula with the term people drop."
    ),
}


# ---------------------------------------------------------------------------
# ex-051 -- agentic tool-calling loop
# ---------------------------------------------------------------------------

EX051 = {
    "slug": "ex-051-the-assistant-kept-calling-the-same-tool",
    "exercise_number": 51,
    "title": "A draft request ran for eleven minutes and cost $40 in tokens",
    "exercise_type": ExerciseType.AGENT_TOOLS,
    "base_app": BaseApp.AGENTDESK,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "step_budget_counts_only_successful_tool_calls",
    "time_limit_minutes": 40,
    "expected_time_minutes": 24,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["agents", "tool-calling", "llm", "reliability", "python"],
    "brief_md": """\
## SUP-1203 — one draft request would not stop

**Reported by:** whoever is on call, at 02:40
**Severity:** SEV-2, and it is a money problem as much as an availability one

A support agent asked for a draft on a ticket. The request never returned. It sat there
making model calls for eleven minutes before the gateway cut it off, and the usage
dashboard for that window shows about $40 of tokens for one unanswered question.

It has happened four times this week. Every one of them is a ticket where the agent's
question made us call a tool that **failed** — a ticket id that does not exist, an
article slug that was renamed.

### What we know

- Runs that succeed are fine. Two or three tool calls and an answer, as designed.
- There **is** a step budget. `AGENTDESK_MAX_STEPS` is 6 and nobody has changed it.
- The gateway cut it off at eleven minutes. Nothing in our code did.

### Reproducing it

```bash
docker compose up -d --wait
make migrate && make seed
make test
```

One of the loop tests is red and names the property directly. Read what it asserts
before you read the implementation — the test is describing a situation, not a line.

### What we need

A run that stops. And a `NOTES.md` that says what the budget was actually counting,
because "we had a budget" was true the whole time and did not help.
""",
    "definition_of_done": [
        "R1: a run whose every tool call fails still stops at the ceiling",
        "R2: the whole suite is green, with no test skipped, deleted or weakened",
        "R3: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md explains what the budget was counting and why that is not the same "
        "as what it should bound",
    ],
    "focus_paths": ["src/agentdesk/assistant/loop.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_loop.py::test_the_budget_counts_rounds_not_successes",
            "weight": 6,
            "required": True,
            "description": "A run of nothing but failing tool calls still reaches the ceiling",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R3",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "CI passes end to end",
        },
        {
            "id": "R4",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, fixtures and generators are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Named the real distinction: the budget was counting *useful* rounds, and "
                "the resource that needs bounding is model calls, which a failed round "
                "spends just as surely as a successful one"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Noticed that the recorded client's own circuit breakers are what turned "
                "this into a failing test rather than a hanging one, and did not mistake "
                "them for the fix"
            ),
        },
    ],
    "grading_notes": """\
**Root cause.** The loop counts *successful* tool calls rather than rounds. A round whose
tool fails does not increment the counter, so a run in which every call fails never
advances towards the ceiling and the ``while`` never terminates. The budget was real the
whole time; it was bounding the wrong thing.

**The expected fix** restores a round-counting loop -- ``for _ in range(ceiling)`` -- so
every pass costs one unit of budget regardless of outcome. Two or three lines.

**Measured:** 1 test fails, ``test_the_budget_counts_rounds_not_successes``. It is the
only one, which makes this a clean exercise in reading an assertion carefully: the test
describes a *situation* (every call in the run fails) rather than a line.

**What separates a strong answer (S1).** "It wasn't counting failures" has found the line.
"The resource being spent is a model call, and a failed round spends one exactly as a
successful round does, so the budget has to bound rounds" has understood what a budget is
for -- and will recognise the same mistake in a retry loop or a rate limiter.

**S2 is the quiet one.** Under this defect the suite *fails* rather than hanging, and only
because ``RecordedClient`` refuses to serve an over-long conversation. A candidate who
notices that the circuit breaker is what made the bug visible -- and does not mistake it
for the fix, or "fix" it by raising the limit -- is reading the system rather than the
stack trace.

**Watch for:**

- **Raising ``MAX_OBSERVATIONS`` or ``RUNAWAY_LIMIT``.** Makes the test pass by moving the
  backstop. The loop still does not terminate; it just takes longer to notice. Treat as
  not solved.
- **Catching the runaway error and returning a refusal.** Converts an unbounded loop into
  an unbounded loop with a nicer ending. Same verdict.
- **Breaking out of the loop on the first tool failure.** Passes the test and removes the
  recovery path that ex-053's exercise depends on: the agent is *supposed* to read its
  error and try again. Mark correctness down.
- **A fix in the recorded client rather than the loop.** The client is not where the
  budget lives.
""",
    "baseline": baseline("ex-051-the-assistant-kept-calling-the-same-tool"),
    "context_excerpts": [
        {
            "path": "src/agentdesk/assistant/loop.py",
            "line_range": "1-20",
            "why": (
                "The module docstring states both of this loop's invariants, including "
                "the one that is broken. Worth reading as the author's intent, then "
                "checking against what the code does."
            ),
        },
        RECORDED_MODEL_EXCERPT,
    ],
    "hints": [
        "Run `make test` and read the failing assertion. It describes a scenario: every "
        "tool call in the run fails. Ask what the loop does differently in that case.",
        "The ceiling is applied somewhere. Find it, then ask what increments the thing it "
        "is compared against.",
        "A failed tool call costs exactly what a successful one costs: a model call. "
        "Which of those two is the budget meant to bound?",
    ],
}


# ---------------------------------------------------------------------------
# ex-052 -- agentic tool-calling loop
# ---------------------------------------------------------------------------

EX052 = {
    "slug": "ex-052-every-tool-answer-vanished-before-the-model-saw-it",
    "exercise_number": 52,
    "title": "The assistant looks up the same ticket over and over, then gives up",
    "exercise_type": ExerciseType.AGENT_TOOLS,
    "base_app": BaseApp.AGENTDESK,
    "difficulty": Difficulty.ADVANCED,
    "defect_class": "tool_result_appended_under_the_wrong_role",
    "time_limit_minutes": 55,
    "expected_time_minutes": 36,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["agents", "tool-calling", "llm", "protocol", "python"],
    "brief_md": """\
## SUP-1247 — every draft comes back empty since the deploy

**Reported by:** the whole support floor
**Severity:** SEV-1, the assistant is unusable

Since yesterday's deploy, **every** draft request fails. The response says the assistant
could not work it out. The logs show it calling `lookup_ticket` on the same ticket six
times in a row, with the same arguments, and then stopping.

Nothing is throwing. The tools are returning data — we checked, the ticket is there and
the tool returns it. The assistant just keeps asking for it.

### What we know

- The deploy touched the agent loop and nothing else.
- Tool calls **succeed**. Their results come back correctly.
- The model is recorded, not live, so this is not the provider behaving oddly.
- `make test` is red in several places. They are all the same bug — resist fixing them
  one at a time.

### Reproducing it

```bash
docker compose up -d --wait
make migrate && make seed
make ask ID=2 Q="What should I tell them about the VPN?"
```

Watch the trace it prints: the same tool, the same arguments, repeatedly.

### Where to start

Read `src/agentdesk/llm/recorded_client.py` first, specifically what the cassette key is
built from. It explains why a loop that is not making progress asks the same question
twice — and the fact that the key is not moving is itself the clue.

### What we need

Drafts that work, and a `NOTES.md` explaining why the model could not tell its request
had been answered. "It got confused" is not an explanation; there is a specific thing it
was looking for and did not find.
""",
    "definition_of_done": [
        "R1: each tool result reaches the model as a tool result, matched to its call",
        "R2: a two-tool question is answered without repeating a tool",
        "R3: tool results are correlated with the calls they answer",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md explains what the model was looking for and did not find",
    ],
    "focus_paths": ["src/agentdesk/assistant/loop.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_loop.py::test_each_observation_reaches_the_model",
            "weight": 5,
            "required": True,
            "description": "Tool results arrive as tool messages carrying their call id",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_loop.py::test_a_two_tool_question_is_answered",
            "weight": 3,
            "required": True,
            "description": "A run that needs two tools completes, calling each once",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_loop.py::test_a_tool_result_is_matched_to_its_call",
            "weight": 2,
            "required": True,
            "description": "Every result names the call it answers",
        },
        {
            "id": "R4",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R5",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "CI passes, including the end-to-end draft",
        },
        {
            "id": "R6",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, fixtures and generators are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Explained that the role carries the meaning: the same characters in an "
                "assistant message are the model's own words quoted back at it, so its "
                "request was never served and it asked again"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Connected the symptom to the cassette key -- the observations digest did "
                "not move, so the model was asked an identical question and gave an "
                "identical answer -- rather than treating the repetition as inexplicable"
            ),
        },
    ],
    "grading_notes": """\
**Root cause.** The tool result is appended as an ``assistant`` message instead of a
``tool`` message carrying the ``tool_call_id`` of the call it answers. The characters are
identical; the role is not. ``observations_digest`` counts only tool-role messages, so the
conversation's observed state never changes, the cassette key never moves, and the model
is asked a question it has already been asked -- so it gives the same answer and requests
the same tool again.

**The expected fix** restores ``role="tool"`` with ``tool_call_id=call.id`` and
``name=call.name``. A handful of lines in one place.

**Measured:** 8 tests fail. They look like several problems and are one; a candidate who
starts fixing them individually has misread the situation and will take far longer.

**What separates a strong answer (S1).** The insight is that the role carries meaning the
content cannot. In an assistant message the same text is the model's own words quoted back
at it, so from the model's point of view its request was never served. A candidate who
articulates that has understood the protocol rather than memorised a field name.

**S2: the diagnostic chain.** The cassette key is the fastest route to this bug -- the key
not moving between rounds is a direct readout of "the model has observed nothing new".
A candidate who uses that, rather than treating the repetition as mysterious, found it the
way the system was designed to be debugged.

**Watch for:**

- **Adding the result to the assistant message's content as well**, so the model "can see
  it". Sometimes passes the end-to-end test and leaves the protocol broken; the tool-role
  assertions will still fail. Not a fix.
- **De-duplicating tool calls** so a repeat is suppressed. Treats the symptom, breaks the
  legitimate case where a tool is called twice with different arguments.
- **Re-recording the cassettes.** ``fixtures/`` is protected, and this would be making the
  recordings agree with the bug.
- **Raising ``max_steps``.** The loop is not short of steps; it is not progressing.
""",
    "baseline": baseline("ex-052-every-tool-answer-vanished-before-the-model-saw-it"),
    "context_excerpts": [
        RECORDED_MODEL_EXCERPT,
        {
            "path": "src/agentdesk/llm/types.py",
            "line_range": "54-76",
            "why": (
                "The ``Message`` docstring states that the role of a tool result is "
                "load-bearing rather than cosmetic, and says exactly what goes wrong when "
                "it is not a tool message. The contract the fix has to restore."
            ),
        },
    ],
    "hints": [
        'Run `make ask ID=2 Q="What should I tell them about the VPN?"` and read the '
        "trace. The same tool, the same arguments, more than once.",
        "The model's next decision is looked up by a key. Find what the key is built "
        "from, then work out why it is not changing between rounds.",
        "The loop appends two messages per tool call. Look carefully at the second one, "
        "and compare it against what `observations_digest` counts as an observation.",
    ],
}


# ---------------------------------------------------------------------------
# ex-053 -- agentic tool-calling loop
# ---------------------------------------------------------------------------

EX053 = {
    "slug": "ex-053-a-made-up-ticket-id-reached-the-database",
    "exercise_number": 53,
    "title": "A tool call with an invented ticket id reached the database",
    "exercise_type": ExerciseType.AGENT_TOOLS,
    "base_app": BaseApp.AGENTDESK,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "tool_arguments_reach_the_handler_unvalidated",
    "time_limit_minutes": 40,
    "expected_time_minutes": 25,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["agents", "tool-calling", "validation", "input-handling", "python"],
    "brief_md": """\
## SUP-1260 — a stack trace in the drafting endpoint

**Reported by:** error tracking, then a support agent who saw a 500
**Severity:** SEV-2

The drafting endpoint threw. The trace bottoms out in psycopg, complaining about an
invalid input syntax for an integer, and the value it was given is the string
`"the printer one"`.

That phrase is not in our code anywhere. It is what the model decided to pass as a
`ticket_id` after reading a ticket that referred to "the printer one" in prose.

### What this is really about

The model is good at producing arguments that *read* correctly. A ticket id of
`"the printer one"`, a status where a priority belongs, an extra `limit` parameter on a
tool that never declared one — all of them look plausible and none of them are valid.

Arguments arriving from a model are input from outside the system. They have the same
standing as a query string.

### Reproducing it

```bash
docker compose up -d --wait
make migrate && make seed
make test
```

The registry tests are red. Read what they assert about *where* a bad argument should
stop.

### What we need

Bad arguments refused before they reach a tool body, with a message the model can read
and act on — it is expected to correct itself on the next round, and it cannot do that
from a 500. And a `NOTES.md` that says why validation belongs where you put it.
""",
    "definition_of_done": [
        "R1: an argument of the wrong type never reaches the handler",
        "R2: every non-integer value is refused where an integer is declared",
        "R3: missing, undeclared and out-of-enum arguments are all refused",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md argues for where validation belongs, not just that it was added",
    ],
    "focus_paths": ["src/agentdesk/assistant/registry.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_registry.py::test_a_hallucinated_identifier_never_reaches_the_handler",
            "weight": 5,
            "required": True,
            "description": "The handler is not called at all when an argument is invalid",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_registry.py::test_things_that_are_not_an_integer_are_refused",
            "weight": 3,
            "required": True,
            "description": "Every non-integer, booleans included, is refused",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_registry.py::test_an_undeclared_argument_is_refused",
            "weight": 2,
            "required": True,
            "description": "An argument the tool never declared is refused rather than dropped",
        },
        {
            "id": "R4",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R5",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "CI passes end to end",
        },
        {
            "id": "R6",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, fixtures and generators are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Framed model output as untrusted input with the same standing as a query "
                "string, rather than as a bug in the model to be worked around"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Noted that the refusal has to be legible to the model, because the "
                "recovery path depends on it reading the error and correcting itself"
            ),
        },
    ],
    "grading_notes": """\
**Root cause.** ``Registry.invoke`` passes ``call.arguments`` straight to the handler,
skipping ``ToolSpec.validate``. Model-produced arguments reach tool bodies -- and from
there the database -- without their declared types, their required set, or their enums
ever being checked.

**The expected fix** restores the validate call. One line of substance; the validation
machinery is already written and tested.

**Measured:** 11 tests fail, nine of them in ``test_registry.py``. The sheer count is the
hint: a single missing step at a boundary invalidates every guarantee downstream of it.

**What separates a strong answer (S1).** The framing. A candidate who treats this as "the
model sometimes sends bad data, so add a check" is patching a nuisance. One who says model
output is untrusted input with the same standing as a query string -- and that the tool
bodies are entitled to assume well-typed arguments precisely *because* the boundary
validates -- is describing why the architecture is shaped this way.

**S2: the error has to be legible.** ``_invoke`` turns ``InvalidArguments`` into an
observation the model reads, and the recorded transcript includes a run where the model
passes a phrase where an integer belongs and recovers on the next round. A candidate who
notices that the refusal is part of the agent's control flow, not just a guard, has seen
the whole mechanism.

**Watch for:**

- **Validating inside each handler.** Works, duplicates the logic per tool, and guarantees
  the next tool added will forget. Accept with a note; mark engineering quality down.
- **Coercing instead of refusing** -- ``int(value)`` in a try/except. Turns "the printer
  one" into a refusal by accident and ``12.9`` into ticket 12 silently. The second is
  worse than the bug.
- **Catching the database error further down.** Treats the symptom at the point where the
  stack trace appeared rather than where the input entered.
- **Accepting booleans as integers.** ``isinstance(True, int)`` is true in Python, so a
  naive check lets ``True`` through as a ticket id; one of the failing parameter cases
  exists specifically for this.
""",
    "baseline": baseline("ex-053-a-made-up-ticket-id-reached-the-database"),
    "context_excerpts": [
        {
            "path": "src/agentdesk/assistant/registry.py",
            "line_range": "1-15",
            "why": (
                "The module docstring sets out the frame the fix depends on -- arguments "
                "from a model are untrusted input -- and says why validation lives at the "
                "boundary rather than in each tool body."
            ),
        },
        {
            "path": "src/agentdesk/assistant/loop.py",
            "line_range": "196-212",
            "why": (
                "``_invoke`` catches exactly three exception types and turns them into "
                "observations the model can read. Which exception a bad argument raises "
                "decides whether the agent recovers or the request 500s."
            ),
        },
    ],
    "hints": [
        "Run `make test` and read the registry failures. Several of them, and they all "
        "concern the same missing step.",
        "`Registry.invoke` is three lines. Compare what it does against what `ToolSpec` offers.",
        "Note that `isinstance(True, int)` is true in Python, so a naive type check lets "
        "a boolean through as a ticket id.",
    ],
}


# ---------------------------------------------------------------------------
# ex-054 -- prompt design
# ---------------------------------------------------------------------------

EX054 = {
    "slug": "ex-054-the-model-stopped-using-half-the-parameters",
    "exercise_number": 54,
    "title": "The assistant never passes a limit, and nobody can work out why",
    "exercise_type": ExerciseType.GENAI_CHATBOT,
    "base_app": BaseApp.AGENTDESK,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "prompt_advertises_fewer_parameters_than_registered",
    "time_limit_minutes": 40,
    "expected_time_minutes": 24,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["prompt-engineering", "agents", "tool-calling", "llm", "python"],
    "brief_md": """\
## SUP-1288 — the assistant ignores parameters that exist

**Reported by:** the engineer who added the parameter
**Severity:** SEV-4, and it has probably been true for a while

`search_tickets` takes a `limit`. It has taken a `limit` since February. The assistant
has never once passed one — it always gets the default five, and in a couple of cases
that has meant missing the ticket the agent was actually looking for.

The same engineer went looking and thinks it is broader than one parameter: as far as
they can tell, **no optional parameter on any tool is ever used**.

### Why this is worth your time

Nothing is failing. The assistant works, the answers are good, and if the parameter had
never been added nobody would notice any difference. That is the point: a capability
exists, the model does not know about it, and there is no error anywhere that would ever
tell you.

### Reproducing it

```bash
docker compose up -d --wait
make migrate && make seed
make test
```

Two prompt tests are red, and they compare two things that are supposed to be the same.

### What we need

The model told about the tools it actually has. And a `NOTES.md` that explains how the
two descriptions came apart, and what makes it impossible for them to come apart again —
"I updated it" is not the answer we are looking for.
""",
    "definition_of_done": [
        "R1: the prompt advertises exactly the registered tool contracts",
        "R2: a newly registered parameter reaches the prompt with no prompt edit",
        "R3: the whole suite is green, with no test skipped, deleted or weakened",
        "R4: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md explains what keeps the two descriptions from drifting again",
    ],
    "focus_paths": ["src/agentdesk/assistant/prompt.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_prompt.py::test_the_prompt_advertises_exactly_the_registered_contract",
            "weight": 5,
            "required": True,
            "description": "What the model is told matches what the registry will accept",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_prompt.py::test_a_new_parameter_reaches_the_prompt_without_anyone_editing_it",
            "weight": 4,
            "required": True,
            "description": "The catalog is rendered from the registry, not restated",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R4",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "CI passes end to end",
        },
        {
            "id": "R5",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, fixtures and generators are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Identified the class of bug -- two descriptions of one contract, with "
                "nothing comparing them -- rather than only the instance, and said why no "
                "amount of care prevents the recurrence while both copies exist"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Observed that this failure is silent by construction: there is no "
                "request that errors, so only a test that compares the two could ever "
                "catch it"
            ),
        },
    ],
    "grading_notes": """\
**Root cause.** ``render_tools`` filters the rendered schema down to required parameters
before showing it to the model. The registry still accepts optional parameters, so the
contract the model is told about is a strict subset of the contract that exists. Every
optional parameter on every tool is invisible.

**The expected fix** removes the filtering so the catalog is rendered from
``ToolSpec.schema()`` unaltered. A few lines.

**Measured:** 2 tests fail, both comparing the prompt's catalog against the registry's.

**What separates a strong answer (S1).** Recognising the class rather than the instance:
two descriptions of one contract with nothing comparing them. The fix is not "I updated
the prompt" -- that is what the original author did, and it drifted again. The fix is that
there is now one description and the other is derived from it. A candidate who says so has
understood why the test asserts equality between two sources rather than checking the
prompt against a fixture.

**S2: the silence.** No request errors under this defect. The assistant works, the answers
are good, and the only observable symptom is a capability nobody uses. A candidate who
articulates that -- that this failure mode is undetectable except by comparison -- has
understood why the test exists in the form it does.

**Watch for:**

- **Hand-editing the prompt to add the missing parameters.** Passes neither test, because
  both compare against the registry, but a candidate may try it first. Note whether they
  recognise why it is the wrong shape of fix.
- **Changing ``ToolSpec.schema()`` instead.** Makes the comparison test pass by moving both
  sides together, while the model is still told less than the truth. Check which side they
  edited -- this one is easy to miss on a quick read of the diff.
- **Marking the optional parameters required.** Makes the symptom go away and changes the
  tool contract to do it.
- **Weakening the test** to compare only names. Protected, but worth watching for in the
  reasoning even when the file is untouched.
""",
    "baseline": baseline("ex-054-the-model-stopped-using-half-the-parameters"),
    "context_excerpts": [
        {
            "path": "src/agentdesk/assistant/prompt.py",
            "line_range": "1-28",
            "why": (
                "The module's first rule is that the tool catalog is rendered and never "
                "written, with the incident that produced the rule -- which is almost "
                "exactly the ticket you have been handed."
            ),
        },
        RECORDED_MODEL_EXCERPT,
    ],
    "hints": [
        "Run `make test`. The failing assertion compares the prompt's tool catalog "
        "against the registry's. Print both and diff them.",
        "`render_tools` builds what the model is shown. Follow what it does to each "
        "schema on the way out.",
        "Ask which parameters survive and which do not. The pattern is the finding.",
    ],
}


# ---------------------------------------------------------------------------
# ex-055 -- prompt design
# ---------------------------------------------------------------------------

EX055 = {
    "slug": "ex-055-a-ticket-closed-the-fence-and-gave-orders",
    "exercise_number": 55,
    "title": "A customer wrote the closing marker themselves",
    "exercise_type": ExerciseType.GENAI_CHATBOT,
    "base_app": BaseApp.AGENTDESK,
    "difficulty": Difficulty.ADVANCED,
    "defect_class": "untrusted_fence_marker_is_forgeable",
    "time_limit_minutes": 55,
    "expected_time_minutes": 35,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["prompt-injection", "security", "prompt-engineering", "llm", "python"],
    "brief_md": """\
## SEC-412 — the injection defence does not hold

**Reported by:** the security review
**Severity:** SEV-1

We fence untrusted ticket text so the model can tell a customer's words from the
operator's. The review found that the fence can be closed by the customer.

Ticket #5 in the seed data is the live example. Its body contains our own closing marker,
followed by text addressed to the model claiming operator authority and instructing it to
escalate and to confirm a refund.

Everything after that marker reads as though **we** wrote it.

### Why this got through review the first time

The fence is there. It looks correct. It *is* correct for every ticket where nobody is
trying — which is every ticket an engineer writes while testing. The failure only exists
when somebody is deliberately looking for it, which is precisely the case that matters.

### Reproducing it

```bash
docker compose up -d --wait
make migrate && make seed
make test
```

Several prompt tests are red. Then look at what the model is actually shown:

```bash
curl -s localhost:$WS_APP_PORT/assistant/fence-preview/5
```

Count the closing markers in what comes back.

### What we need

A fence a customer cannot close, open, or otherwise forge — and the customer's text still
**shown**, in full, because the desk needs to read what they wrote. Suppressing it is not
a fix.

`NOTES.md` should say what property a fence has to have to be worth anything.
""",
    "definition_of_done": [
        "R1: a forged closing marker cannot end the fence early",
        "R2: a forged opening marker cannot start a new one",
        "R3: the fence preview endpoint shows a defused ticket #5",
        "R4: ordinary angle brackets in customer text survive untouched",
        "R5: the whole suite is green, with no test skipped, deleted or weakened",
        "R6: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md states the property that makes a fence meaningful",
    ],
    "focus_paths": ["src/agentdesk/assistant/prompt.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_prompt.py::test_a_forged_closing_marker_cannot_escape_the_fence",
            "weight": 5,
            "required": True,
            "description": "Customer text cannot close the fence early",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_prompt.py::test_a_forged_opening_marker_is_neutralized_too",
            "weight": 3,
            "required": True,
            "description": "Nor open a new one under a label the operator never used",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_api.py::test_the_fence_preview_shows_a_neutralized_marker",
            "weight": 2,
            "required": True,
            "description": "An operator can confirm the live payload was defused",
        },
        {
            "id": "R4",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_prompt.py::test_ordinary_angle_brackets_survive",
            "weight": 2,
            "required": True,
            "description": "Pasted logs and code are not mangled by the fix",
        },
        {
            "id": "R5",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R6",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "CI passes end to end",
        },
        {
            "id": "R7",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, fixtures and generators are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Stated the property rather than the patch: a delimiter is only a boundary "
                "if the content cannot contain it, so the content must be transformed "
                "before it is placed inside"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Handled the opening marker as well as the closing one, and explained why "
                "a forged opener is as dangerous -- text after it is attributed to a label "
                "the operator never used"
            ),
        },
    ],
    "grading_notes": """\
**Root cause.** ``fence`` interpolates untrusted content without transforming it, so a
ticket body containing the closing marker ends the fence early. Everything after it is
rendered outside the fence and reads to the model as operator instruction. Ticket #5 in
the seed data carries exactly this payload.

**The expected fix** restores the substitution that replaces marker-shaped text in the
content before fencing. One line, and the difficulty is entirely in seeing why it is
needed.

**Measured:** 7 tests fail, including the API's fence-preview check against the live
payload.

**What separates a strong answer (S1).** The property, stated generally: a delimiter only
marks a boundary if the delimited content cannot contain it. That is the same reasoning
behind escaping in SQL, in shells, in HTML, and in every MIME multipart boundary -- a
candidate who makes that connection is not going to write this bug again in a different
syntax.

**S2: both directions.** Neutralising only the closing marker leaves the forged *opening*
marker, after which text is attributed to a label the operator never used -- just as
dangerous and easier to overlook because it is not what the ticket reported. The test is
there; the question is whether the candidate understood it or just made it green.

**Also worth credit:** noticing that suppressing or stripping the attacking text would be
the wrong fix. The desk has to read what the customer wrote. The defence is attribution,
not censorship, and the system prompt instructs the model to mention such attempts.

**Watch for:**

- **Rejecting or blanking tickets that contain markers.** Secure and useless; the support
  agent can no longer see the ticket. Mark correctness down even if tests pass.
- **Escaping only the exact closing marker for the current label.** Fails the opening-marker
  test, and is the narrow fix the ticket's wording invites.
- **Choosing a longer or random delimiter.** Raises the cost of forgery without removing
  it, and a random delimiter that varies per request would move every cassette key. If a
  candidate proposes a nonce, ask what it costs here.
- **Over-broad escaping** that mangles ordinary ``<`` characters. There is a test for it,
  because customers paste logs.
""",
    "baseline": baseline("ex-055-a-ticket-closed-the-fence-and-gave-orders"),
    "context_excerpts": [
        {
            "path": "src/agentdesk/assistant/prompt.py",
            "line_range": "16-28",
            "why": (
                "The module's second rule, which states the exact failure the security "
                "review found: a fence that interpolates unchecked is theatre, correct in "
                "every example where the attacker is not trying."
            ),
        },
        {
            "path": "tools/gen_fixtures.py",
            "line_range": "88-100",
            "why": (
                "``FORGED_FENCE_BODY`` -- the payload carried by ticket #5, kept in one "
                "constant so the test and the seed data cannot drift apart."
            ),
        },
    ],
    "hints": [
        "Run `curl -s localhost:$WS_APP_PORT/assistant/fence-preview/5` and count the "
        "closing markers. There should be one.",
        "`fence()` builds the block. Look at what happens to `content` on its way in.",
        "A delimiter only marks a boundary if the thing inside cannot contain it. What "
        "has to be true of the content before it is placed between the markers?",
    ],
}


# ---------------------------------------------------------------------------
# ex-056 -- integration latency
# ---------------------------------------------------------------------------

EX056 = {
    "slug": "ex-056-the-ticket-list-times-out-whenever-drafts-are-busy",
    "exercise_number": 56,
    "title": "The ticket list times out, and the ticket list has not changed",
    "exercise_type": ExerciseType.LATENCY,
    "base_app": BaseApp.AGENTDESK,
    "difficulty": Difficulty.ADVANCED,
    "defect_class": "pooled_connection_held_across_the_model_call",
    "time_limit_minutes": 55,
    "expected_time_minutes": 36,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["latency", "connection-pool", "integration", "agents", "python"],
    "brief_md": """\
## SUP-1310 — the queue page times out at busy times

**Reported by:** two support leads, independently
**Severity:** SEV-1 during business hours

The ticket queue page times out. Not slowly — it hangs and then returns a 500 about
connection acquisition. It clears up within a minute.

Both reports are from mid-morning, which is when the floor is busiest. Neither lead uses
the assistant. One of them did not know we had one.

### What we know

- `tickets/` has not been deployed in three weeks. The last deploy was to `assistant/`.
- The pool is 10 connections and has been 10 for two years.
- The queue page makes one query. It is not the query that is slow.
- It always coincides with several drafts being generated at once.

### A warning about how to approach this

Do not reach for a profiler, and do not widen the pool. The pool size is deliberate — the
module docstring in `src/agentdesk/db.py` explains why a generous pool makes this class
of bug **harder** to find, not easier.

The guarantees this repository makes about latency are structural, not timed. Read
`src/agentdesk/obs/probes.py` to see what is actually being asserted and why, then run:

```bash
docker compose up -d --wait
make migrate && make seed
make test
```

One test is red and it names the resource.

### What we need

The desk unaffected by how busy the assistant is. And a `NOTES.md` that explains the
arithmetic: why ten connections and a one-second generation produce exactly this symptom.
""",
    "definition_of_done": [
        "R1: no pooled connection is held while a model call is in flight",
        "R2: the whole suite is green, with no test skipped, deleted or weakened",
        "R3: bash ci/run_ci.sh exits 0",
        "R4: the pool size is unchanged",
        "llm: NOTES.md does the arithmetic linking pool size and generation time to the "
        "symptom the leads reported",
    ],
    "focus_paths": ["src/agentdesk/assistant/service.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_integration_latency.py::test_no_connection_is_held_across_a_model_call",
            "weight": 6,
            "required": True,
            "description": "No connection span overlaps a model span",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R3",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "CI passes end to end",
        },
        {
            "id": "R4",
            "kind": CheckKind.GREP_PRESENT,
            "target": 'AGENTDESK_POOL_MAX", "10"',
            "paths": ["src/agentdesk/config.py"],
            "weight": 2,
            "required": True,
            "description": "The pool was not widened to paper over the problem",
        },
        {
            "id": "R5",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, fixtures and generators are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Did the arithmetic: ten connections, a generation of roughly a second, "
                "and ten concurrent drafts own the whole pool -- which is why the symptom "
                "lands on an endpoint that did not change"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Explained why widening the pool or adding a timeout would have hidden "
                "the problem rather than fixed it"
            ),
        },
    ],
    "grading_notes": """\
**Root cause.** ``draft_reply`` wraps the whole request -- read, generate, write -- in a
single ``db.connection()``, so one pooled connection is held for the duration of the model
call. The pool is ten. Ten concurrent drafts own all of it, and the ticket queue, which
has not been deployed in three weeks, starts failing to acquire a connection.

**The expected fix** restores the three-beat shape the module docstring describes: read
with its own connection, release, generate holding nothing, then write with its own
connection.

**Measured:** 1 test fails, naming the connection token that was open when the model call
started.

**What separates a strong answer (S1).** The arithmetic, done explicitly: pool of ten,
generation of roughly a second, ten concurrent drafts, and the desk is out of connections
for a second at a time. That is what turns "the queue page is slow" into a prediction you
can check -- and it explains the detail in the ticket that matters most, which is that the
symptom appears in an endpoint nobody changed.

**S2: the fixes not taken.** Widening the pool and adding an acquisition timeout both make
the reported symptom quieter. Neither stops the assistant consuming a connection it is not
using. A candidate who says why those are worse than nothing -- they raise the concurrency
needed before anyone notices -- has understood ``config.py``'s comment about why the pool
is deliberately small.

**Watch for:**

- **Raising ``AGENTDESK_POOL_MAX``.** There is a required grep check against this
  specifically. It is the first thing most people reach for.
- **Moving the model call out of the transaction but keeping the connection open.** The
  connection is the scarce resource, not the transaction.
- **Making the draft endpoint async-only or queueing it.** A real design option, much
  larger than this ticket, and it does not address the handler holding a connection.
- **Fixing ``draft_reply`` and not checking ``summarize_for_intake``.** Intake also calls a
  model, on the ticket-creation request. It is correct in this exercise, but a candidate
  who does not look has been lucky rather than thorough.
""",
    "baseline": baseline("ex-056-the-ticket-list-times-out-whenever-drafts-are-busy"),
    "context_excerpts": [
        MECHANISM_NOT_CLOCK_EXCERPT,
        {
            "path": "src/agentdesk/assistant/service.py",
            "line_range": "1-21",
            "why": (
                "The module docstring states the three-beat shape every handler here is "
                "supposed to have -- read, generate, write -- and what happens when the "
                "generate step is folded inside the read's connection."
            ),
        },
        {
            "path": "src/agentdesk/config.py",
            "line_range": "25-40",
            "why": (
                "Why the pool is ten and deliberately not larger: a generous pool hides "
                "exactly this bug, because it takes proportionally more concurrency before "
                "anybody notices."
            ),
        },
    ],
    "hints": [
        "Run `make test` and read the failing assertion. It names a connection token and "
        "says when it was held.",
        "`agentdesk.db.connection()` is the only place a connection is checked out, and "
        "it records a span. Find every span that is open when a model call starts.",
        "Work out what the handler's control flow actually is, as opposed to what its "
        "docstring says it should be.",
    ],
}


# ---------------------------------------------------------------------------
# ex-057 -- integration latency
# ---------------------------------------------------------------------------

EX057 = {
    "slug": "ex-057-one-slow-draft-freezes-every-other-request",
    "exercise_number": 57,
    "title": "Health checks fail while a draft is being generated",
    "exercise_type": ExerciseType.LATENCY,
    "base_app": BaseApp.AGENTDESK,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "blocking_model_call_on_the_event_loop",
    "time_limit_minutes": 40,
    "expected_time_minutes": 24,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["latency", "asyncio", "event-loop", "agents", "python"],
    "brief_md": """\
## SUP-1322 — the orchestrator keeps restarting a healthy container

**Reported by:** platform
**Severity:** SEV-2, and it is causing its own outages

The orchestrator has restarted the app container eleven times in two days. Every restart
follows a failed health check. Every failed health check lands during a draft request.

The container is fine. `/health` is three lines and touches almost nothing. It is simply
not being served while a draft is in progress — and neither is anything else.

### What we know

- One draft at a time is enough to do it. This is not a load problem.
- Every endpoint stalls, not only the assistant's.
- The restarts are now causing more disruption than the original symptom.

### Reproducing it

```bash
docker compose up -d --wait
make migrate && make seed
make test
```

One test is red. It compares two thread identifiers — not two timings — and the module
docstring in `src/agentdesk/obs/probes.py` explains why it is written that way.

### What we need

A draft that does not stop the process serving everything else. And a `NOTES.md` that
explains why one slow call takes down endpoints that have nothing to do with it.
""",
    "definition_of_done": [
        "R1: the model call does not run on the event loop thread",
        "R2: other coroutines make progress while a draft is generated",
        "R3: the whole suite is green, with no test skipped, deleted or weakened",
        "R4: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md explains why an unrelated endpoint is the one that fails",
    ],
    "focus_paths": ["src/agentdesk/assistant/service.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_integration_latency.py::test_the_model_call_does_not_run_on_the_event_loop",
            "weight": 6,
            "required": True,
            "description": "Model calls are recorded on a thread that is not the loop's",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_integration_latency.py::test_the_loop_keeps_running_while_a_draft_is_generated",
            "weight": 3,
            "required": True,
            "description": "A cooperating task still advances during a draft",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R4",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "CI passes end to end",
        },
        {
            "id": "R5",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, fixtures and generators are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Explained the mechanism: a synchronous call on the loop thread stops "
                "every coroutine in the process, which is why the health check -- the "
                "endpoint least related to the assistant -- is the one that fails"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Checked the other model-calling path as well, rather than fixing only "
                "the handler named in the ticket"
            ),
        },
    ],
    "grading_notes": """\
**Root cause.** ``draft_reply`` calls ``_draft_sync`` directly instead of handing it to
``asyncio.to_thread``. The model call therefore runs on the event loop thread, and while
it runs no other coroutine in the process is scheduled -- including ``/health``, which is
why the orchestrator keeps restarting a container that is fine.

**The expected fix** restores the ``await asyncio.to_thread(...)`` wrapper. One call.

**Measured:** 1 test fails. It compares thread identifiers, not durations, which is worth
pointing out to a candidate who expected a timing assertion.

**What separates a strong answer (S1).** Explaining why the *least related* endpoint is
the one that failed. A single-threaded event loop means one blocking call stops everything
cooperatively scheduled on it; the health check is affected not because it is slow but
because it is on the same loop. A candidate who says that has understood async, as opposed
to having learned that ``to_thread`` makes a test pass.

**S2: the second path.** ``summarize_for_intake`` calls a model too, on the
ticket-creation request. It is correct here, but the candidate should have checked -- the
same mistake is easy to make twice and the ticket names only one handler.

**Worth noting either way:** a candidate who observes that the test asserts thread identity
*because* a duration threshold would be flaky on a shared runner has read
``obs/probes.py`` and taken the point.

**Watch for:**

- **Making ``_draft_sync`` itself async** without making anything inside it await. The
  function still blocks; the test still fails. A common first attempt.
- **Wrapping in ``run_in_executor`` with a hand-rolled executor.** Equivalent and more
  code. Accept it; ask whether they knew ``to_thread`` existed.
- **Spawning a thread per request manually.** Works, unbounded, and worse under the load
  that produced the ticket.
- **Raising the health check timeout.** Hides the restarts and leaves every other endpoint
  stalled.
""",
    "baseline": baseline("ex-057-one-slow-draft-freezes-every-other-request"),
    "context_excerpts": [
        MECHANISM_NOT_CLOCK_EXCERPT,
        {
            "path": "src/agentdesk/assistant/service.py",
            "line_range": "1-21",
            "why": (
                "States that the model call belongs off the event loop and what happens "
                "when it is not -- including that the health check is among the casualties."
            ),
        },
    ],
    "hints": [
        "Run `make test`. The failing assertion compares a thread id against the one the "
        "test is running on.",
        "`draft_reply` is a coroutine. Look at what each of its steps does with the blocking work.",
        "There is more than one place in this module that calls the model. Check both.",
    ],
}


# ---------------------------------------------------------------------------
# ex-058 -- integration latency
# ---------------------------------------------------------------------------

EX058 = {
    "slug": "ex-058-the-dashboard-got-slower-with-every-ticket",
    "exercise_number": 58,
    "title": "Model spend tripled the month the queue page got slow",
    "exercise_type": ExerciseType.LATENCY,
    "base_app": BaseApp.AGENTDESK,
    "difficulty": Difficulty.BEGINNER,
    "defect_class": "cached_summary_regenerated_per_row",
    "time_limit_minutes": 30,
    "expected_time_minutes": 17,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["latency", "caching", "agents", "llm-cost", "python"],
    "brief_md": """\
## SUP-1341 — the dashboard is slow, and getting slower

**Reported by:** account management
**Severity:** SEV-3

The dashboard takes about twelve seconds for our largest customer and under a second for
a small one. It used to be fast for everybody.

Finance also asked why model spend tripled last month. Nobody has connected the two.

### What we know

- The page renders correctly. Every row looks right.
- It is one database query, and the query is fast.
- The slowness scales with how many rows are shown.

### How summaries are supposed to work

Every ticket gets a one-line summary generated **once**, when it is created, and stored
in a column. Everything after that reads the column. Tickets older than that column have
no summary and fall back to truncating the subject, which is fine and is why the
dashboard can afford never to call a model.

### Reproducing it

```bash
docker compose up -d --wait
make migrate && make seed
make test
make dashboard
```

`make dashboard` prints how many model calls rendering the page took. On a healthy build
that number is zero.

### What we need

A dashboard whose cost does not depend on how many rows it shows, and a `NOTES.md` saying
what the cached column is for.
""",
    "definition_of_done": [
        "R1: rendering the dashboard makes no model calls",
        "R2: a ticket with no cached summary still makes no model call",
        "R3: the whole suite is green, with no test skipped, deleted or weakened",
        "R4: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md explains why the page still looked correct the whole time",
    ],
    "focus_paths": ["src/agentdesk/assistant/digest.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_integration_latency.py::test_the_queue_digest_makes_no_model_calls",
            "weight": 6,
            "required": True,
            "description": "Zero model calls to render a 25-row page",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_integration_latency.py::test_a_ticket_with_no_summary_does_not_trigger_a_model_call",
            "weight": 3,
            "required": True,
            "description": "The fallback path does not reach for a model either",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R4",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "CI passes, including its own zero-model-calls gate",
        },
        {
            "id": "R5",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, fixtures and generators are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Connected the two reports -- the slow page and the model spend -- and "
                "explained why a failure that renders correctly is harder to notice than "
                "one that errors"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Noted that the fallback for summary-less tickets is what makes 'never "
                "call a model here' affordable, rather than treating it as a gap"
            ),
        },
    ],
    "grading_notes": """\
**Root cause.** ``_line`` regenerates each row's summary through the agent instead of
reading the cached ``summary`` column, so rendering a 25-row dashboard makes 25 model
calls. The generated text is fine and the page renders identically, which is why nobody
connected the slow page to the tripled model spend.

**The expected fix** restores ``ticket.display_summary``. One line, and the regeneration
helper goes with it.

**Measured:** 2 tests fail, both counting model calls -- one on a full page, one on the
single-row case where no summary is cached.

**What separates a strong answer (S1).** Connecting the two reports. The ticket contains
the slow dashboard and the finance question as separate facts, and they are the same fact.
A candidate who joins them -- and who notes that a failure which renders correctly is far
harder to notice than one that errors -- is reading the ticket rather than the test.

**S2: the fallback.** Tickets older than the summary column have none, and
``display_summary`` falls back to truncating the subject. That fallback is what makes
"never call a model here" affordable. A candidate who sees it as a deficiency and
"improves" it by generating on demand has reintroduced the bug on a slower schedule.

**Measured cost, if they ask:** the assertion is zero model calls, not few. A dashboard
that calls the model once per *page* would pass a "small" threshold and still scale with
the number of pages.

**Watch for:**

- **Caching the regenerated summaries in memory.** Fast on the second request, still N
  calls on the first, and the column already exists.
- **Reducing ``DIGEST_ROWS``.** Fewer calls per page, same cost per ticket.
- **Generating only for tickets with no cached summary.** Sounds principled, is still a
  model call on a list view, and the seed data contains such a ticket precisely so this
  shows up. The second failing test covers it.
- **Making the regeneration async or batched.** Addresses latency, not spend, and leaves a
  list view calling a model.
""",
    "baseline": baseline("ex-058-the-dashboard-got-slower-with-every-ticket"),
    "context_excerpts": [
        {
            "path": "src/agentdesk/assistant/digest.py",
            "line_range": "1-18",
            "why": (
                "The module docstring states its single design constraint -- no model "
                "calls -- and describes this exact regression as the thing it exists to "
                "prevent."
            ),
        },
        {
            "path": "src/agentdesk/tickets/models.py",
            "line_range": "1-8",
            "why": (
                "Why ``summary`` is a cached column and what it means for it to be absent "
                "on older tickets."
            ),
        },
    ],
    "hints": [
        "Run `make dashboard` and look at the last line, which counts model calls.",
        "`queue_digest` builds the page one row at a time. Read what `_line` does for each row.",
        "The summary is supposed to come from somewhere that costs nothing. Where?",
    ],
}


# ---------------------------------------------------------------------------
# ex-059 -- model serving
# ---------------------------------------------------------------------------

EX059 = {
    "slug": "ex-059-the-server-throws-away-work-it-already-started",
    "exercise_number": 59,
    "title": "Under load the model server abandons requests it already accepted",
    "exercise_type": ExerciseType.MODEL_SERVING,
    "base_app": BaseApp.AGENTDESK,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "kv_reservation_sized_on_prompt_not_peak",
    "time_limit_minutes": 45,
    "expected_time_minutes": 28,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["gpu", "kv-cache", "serving", "capacity", "python"],
    "brief_md": """\
## INF-207 — the server preempts under ordinary load

**Reported by:** inference platform
**Severity:** SEV-2

Our self-hosted model server has started preempting requests during normal business
load. Preemption throws away a request's cache and restarts it later, so a user who was
being streamed an answer watches it stop and begin again.

It only happens once a batch is well into generating. The first few seconds are fine.

### What you are working on, and what you are not

`src/agentdesk/serving/` is the **control plane** — the arithmetic that decides whether a
request may start, and the paged allocator that hands out cache blocks. There is no GPU
here, no CUDA and no inference. The module docstring in `serving/memory.py` is explicit
about that boundary.

That is not a simplification for the exercise. Production OOMs in a serving stack are
almost always planning errors: the card did what it was told and was told wrong.

### What we know

- Preemption is a recovery path. It exists for when the planner was wrong.
- A server preempting under ordinary load is telling you its arithmetic is broken, not
  that it is busy.
- Short answers never trigger it. Long ones do.

### Reproducing it

```bash
docker compose up -d --wait
make test
make plan
```

The scheduler tests are red. One of them fills the server and then lets every request
generate its whole answer.

### What we need

Admission that does not accept more work than can finish, and a `NOTES.md` showing the
arithmetic — including why a load test with short replies would never have caught this.
""",
    "definition_of_done": [
        "R1: a full batch runs to completion without preempting anybody",
        "R2: an admitted request reserves what it will occupy at its peak",
        "R3: reservations and physical blocks remain different numbers",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md shows the arithmetic and why short answers hide the bug",
    ],
    "focus_paths": ["src/agentdesk/serving/scheduler.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_serving_scheduler.py::test_a_full_batch_runs_to_completion_without_preempting",
            "weight": 6,
            "required": True,
            "description": "Nothing is evicted once the server is full and generating",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_serving_scheduler.py::test_an_admitted_request_reserves_its_peak",
            "weight": 3,
            "required": True,
            "description": "The reservation covers prompt plus everything it may generate",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_serving_scheduler.py::test_reservations_and_physical_blocks_are_different_numbers",
            "weight": 2,
            "required": True,
            "description": "Allocation stays lazy; the fix does not become eager reservation",
        },
        {
            "id": "R4",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R5",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "CI passes end to end",
        },
        {
            "id": "R6",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, fixtures and generators are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Explained that the KV cache holds the prompt *and* everything generated "
                "so far, so a request's peak is at its last token, and sizing on the "
                "prompt is correct for about one second"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Noted that a load test with short answers cannot find this, and that "
                "preemption under ordinary load is a symptom of broken admission "
                "arithmetic rather than of being busy"
            ),
        },
    ],
    "grading_notes": """\
**Root cause.** ``Scheduler.admit`` reserves ``blocks_needed(request.prompt_tokens)``
instead of ``request.peak_tokens``. The KV cache holds the prompt *and* every token
generated so far, so a request's peak is at its last token, not its first. Admission
therefore accepts a batch that fits at token 0 and cannot fit at token 200, and the
allocator's only recourse is preemption.

**The expected fix** reserves against ``peak_tokens``. One line.

**Measured:** 5 tests fail. The important one fills the server and then generates every
answer to completion -- with the correct reservation it admits 67 requests and preempts
nobody; with the defect it admits 81 and preempts 14.

**What separates a strong answer (S1).** Saying where the peak is and why. "The cache
grows with every generated token, so sizing admission on the prompt is correct for about
one second" is the whole insight, and it generalises to any resource reserved against a
starting size rather than a final one.

**S2: why nothing caught it.** A load test with short answers never reaches the point of
failure, and preemption makes the server *look* like it is coping. A candidate who notes
that preemption under ordinary load is a symptom of broken admission arithmetic rather
than of being busy has understood what the recovery path is for.

**Watch for:**

- **Allocating the peak eagerly** as well as reserving it. Passes the headline test and
  fails the one asserting that reservations and physical blocks are different numbers --
  it turns paging back into contiguous reservation and wastes most of the card.
- **Disabling or softening preemption.** Removes the evidence. The requests still cannot
  all finish.
- **Shrinking ``max_new_tokens``** so more requests fit. Changes the product to suit the
  arithmetic.
- **Adding a safety margin** -- reserving prompt times some factor. Works for the tested
  shape, is not the quantity that matters, and will be wrong for a different ratio of
  prompt to answer.
""",
    "baseline": baseline("ex-059-the-server-throws-away-work-it-already-started"),
    "context_excerpts": [
        VRAM_EXCERPT,
        {
            "path": "src/agentdesk/serving/scheduler.py",
            "line_range": "1-30",
            "why": (
                "Why admission reserves while allocation pages, and what breaks when "
                "either half is dropped -- including the exact failure in this ticket."
            ),
        },
    ],
    "hints": [
        "Run `make test` and read the scheduler failures. One of them fills the server "
        "and then generates to completion.",
        "`Scheduler.admit` computes how many blocks to set aside. Compare that figure "
        "against what the request will hold at its largest.",
        "`Request` exposes more than one notion of size. Which one is admission using?",
    ],
}


# ---------------------------------------------------------------------------
# ex-060 -- model serving
# ---------------------------------------------------------------------------

EX060 = {
    "slug": "ex-060-the-model-server-admits-fewer-requests-every-hour",
    "exercise_number": 60,
    "title": "Capacity falls all day and a restart fixes it",
    "exercise_type": ExerciseType.MODEL_SERVING,
    "base_app": BaseApp.AGENTDESK,
    "difficulty": Difficulty.BEGINNER,
    "defect_class": "kv_blocks_never_returned_on_completion",
    "time_limit_minutes": 30,
    "expected_time_minutes": 18,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["gpu", "kv-cache", "serving", "resource-leak", "python"],
    "brief_md": """\
## INF-219 — capacity decays through the day

**Reported by:** inference platform
**Severity:** SEV-2

The model server accepts fewer and fewer concurrent requests as the day goes on. By late
afternoon it is refusing work it accepted happily at nine in the morning, with no change
in the size of the requests.

Restarting the process fixes it completely, until the next day.

### What you are working on, and what you are not

`src/agentdesk/serving/` is the control plane — the arithmetic and the block accounting.
There is no GPU here and nothing runs inference. The bug is in the bookkeeping, which is
where this class of bug lives in real stacks too.

### What we know

- Nothing errors. Nothing crashes. The server just gets smaller.
- A restart restores it exactly, which says the state is in the process.
- Blocks are not reference counted and nothing reclaims them later.

### Reproducing it

```bash
docker compose up -d --wait
make test
```

The scheduler tests are red. One of them runs a batch to completion and then asks whether
the server is as capable as it was before.

### What we need

Capacity that comes back, and a `NOTES.md` naming the two things a finished request has
to release — they are different, and releasing only one produces a different symptom.
""",
    "definition_of_done": [
        "R1: completing a batch restores the server to full capacity",
        "R2: the allocator's books balance after churn, including after preemption",
        "R3: the whole suite is green, with no test skipped, deleted or weakened",
        "R4: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md names both things a finished request releases and how the two "
        "failure modes differ",
    ],
    "focus_paths": ["src/agentdesk/serving/scheduler.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_serving_scheduler.py::test_completion_returns_capacity_for_the_next_request",
            "weight": 6,
            "required": True,
            "description": "The server admits as many requests after a batch as before it",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_serving_scheduler.py::test_preemption_keeps_the_books_balanced",
            "weight": 3,
            "required": True,
            "description": "The recovery path returns its blocks too",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R4",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "CI passes end to end",
        },
        {
            "id": "R5",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, fixtures and generators are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Distinguished the two leaks: dropping the reservation without freeing the "
                "blocks shrinks physical capacity, while freeing the blocks without "
                "dropping the reservation leaves memory available that admission refuses "
                "to spend"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Observed that a silent leak is worse than a crash here, and noted what "
                "``check_invariants`` is for"
            ),
        },
    ],
    "grading_notes": """\
**Root cause.** ``Scheduler.complete`` drops the request from ``_running`` without calling
``allocator.free``. Blocks are not reference counted and nothing reclaims them later, so
every completed request permanently shrinks the pool. Nothing errors; the server simply
admits less work each hour, and a restart resets it because the state is in the process.

**The expected fix** restores the ``free`` call. One line.

**Measured:** 2 tests fail -- one comparing admitted-request counts before and after a
batch, one covering the preemption path.

**What separates a strong answer (S1).** Naming both things a finished request releases,
and distinguishing the two failure modes: dropping the reservation without freeing blocks
shrinks physical capacity, while freeing blocks without dropping the reservation leaves
memory available that admission refuses to spend. They look identical from outside -- "the
server got smaller" -- and have opposite fixes. A candidate who separates them is thinking
about the mechanism rather than the symptom.

**S2: why silence is the problem.** A leak that crashed would be fixed the same day. This
one degrades gradually, is masked by restarts, and will be attributed to load. The
candidate should notice ``check_invariants`` and say what it is for -- a place for a leak
to be caught rather than inferred.

**This is a beginner exercise and the fix is one line.** Grade the explanation
accordingly: finding it quickly is expected, and the differentiation is entirely in
whether they can say why it was invisible.

**Watch for:**

- **Calling ``free`` in ``decode_step`` instead of ``complete``.** Works for the normal
  path, misses preemption, and the second test covers that.
- **Adding periodic reclamation or a sweep.** Treats leaked blocks as a fact of life rather
  than a bug, and introduces timing to a module that has none.
- **Growing the pool** to compensate. The pool is derived from the card; this is inventing
  memory.
- **Catching the resulting ``OutOfBlocks`` and restarting the server.** Somebody will
  suggest it. It is the production workaround, not the fix.
""",
    "baseline": baseline("ex-060-the-model-server-admits-fewer-requests-every-hour"),
    "context_excerpts": [
        {
            "path": "src/agentdesk/serving/blocks.py",
            "line_range": "1-30",
            "why": (
                "Why the cache is paged, and the paragraph stating that blocks are only "
                "returned by ``free`` -- nothing reclaims them later and they are not "
                "reference counted."
            ),
        },
        {
            "path": "src/agentdesk/serving/scheduler.py",
            "line_range": "1-30",
            "why": (
                "Reservation and allocation are two separate mechanisms, which is what "
                "makes 'release both' a real instruction rather than a tautology."
            ),
        },
    ],
    "hints": [
        "Run `make test` and read the failing assertion: it compares how many requests "
        "the server admits before and after a batch.",
        "`Scheduler.complete` is what runs when a request finishes. Read its docstring, "
        "then read the body.",
        "A finished request holds two different things. Check that the code releases both.",
    ],
}


EXERCISES: list[dict] = [
    EX051,
    EX052,
    EX053,
    EX054,
    EX055,
    EX056,
    EX057,
    EX058,
    EX059,
    EX060,
]
