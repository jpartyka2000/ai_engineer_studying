"""The fixture set and the code must still agree.

This file exists because of a specific failure mode. The cassette key is a hash of the
model, the system prompt and the rendered user prompt -- and the rendered prompt embeds
the schema section built from the catalog. Rename a column, reword an instruction, add a
table, and **every key moves at once**. Nothing crashes at import. The service simply
stops finding recordings, and the first thing anybody notices is a wall of unrelated
failures somewhere else.

So these tests check the join between the three artefacts rather than any one of them:
the transcript, the cassettes derived from it, and the live prompt-assembly code that
computes keys at request time. If they disagree, the failure is here, it is one test, and
it says what to re-run.

``test_a_comparative_question_still_generates_a_cte`` is the odd one out and the most
important. It asserts a property of the *content*: that an ordinary business question
produces SQL with a common table expression. Several tenant-isolation tests downstream
depend on that being true for a question no attacker had to craft. If the recordings were
ever rewritten into flat SQL, those tests would keep passing while quietly testing
nothing -- which is the exact shape of bug this suite is built to refuse.
"""

from __future__ import annotations

import json

import pytest
import sqlglot

from sqlgenie.config import MODEL
from sqlgenie.llm.recorded_client import CassetteMissError, cassette_key
from sqlgenie.nl2sql import prompt as prompt_module
from sqlgenie.nl2sql.policy.row_level_policy import PolicyError, enforce_tenant_scope
from tests.conftest import recording_by_id


def test_every_recording_resolves_to_a_cassette(recordings, client) -> None:
    """The join that matters: what was recorded is what the service will look up.

    Computed through the real prompt assembly, not through the generator script, so an
    edit to the prompt or the catalog fails here rather than at request time.
    """
    missing = []
    for row in recordings:
        rendered = prompt_module.build_prompt(row["question"])
        key = cassette_key(model=MODEL, system=prompt_module.SYSTEM_PROMPT, prompt=rendered)
        if not (client.cassette_dir / f"{key}.json").is_file():
            missing.append(f"{row['id']} ({row['question'][:50]})")
    assert not missing, (
        f"{len(missing)} recording(s) have no cassette: {missing[:5]}. "
        "The prompt or the catalog changed; re-run `make cassettes`."
    )


def test_there_are_no_orphan_cassettes(recordings, client) -> None:
    """A cassette no question can reach is a response nobody can review."""
    expected = {
        cassette_key(
            model=MODEL,
            system=prompt_module.SYSTEM_PROMPT,
            prompt=prompt_module.build_prompt(row["question"]),
        )
        for row in recordings
    }
    assert set(client.keys()) == expected


def test_the_cassette_count_matches_the_transcript(recordings, client) -> None:
    assert len(client.keys()) == len(recordings) == 31


def test_every_cassette_round_trips(recordings, client) -> None:
    """Fetching through the client returns the SQL the transcript authored."""
    for row in recordings:
        generation = client.generate(
            system=prompt_module.SYSTEM_PROMPT,
            prompt=prompt_module.build_prompt(row["question"]),
        )
        assert generation.sql == row["sql"], row["id"]


def test_a_miss_is_an_error_not_a_fallback(client) -> None:
    """There is no network path out of this service, and a miss must prove it."""
    with pytest.raises(CassetteMissError, match="no cassette"):
        client.generate(system="different system prompt", prompt="unrecorded question")


# ---------------------------------------------------------------------------
# Content properties the rest of the suite depends on
# ---------------------------------------------------------------------------


def test_a_comparative_question_still_generates_a_cte(recordings) -> None:
    """**The load-bearing content assertion.**

    b05 is an ordinary question Finance asks every month. Its recorded SQL builds each
    side as a common table expression, so both of its reads of ``orders`` live inside
    CTE bodies rather than in the statement's outer scope.

    That is what makes the tenant-isolation tests meaningful: the dangerous shape
    arrives through a question nobody had to craft. Flatten this recording and those
    tests still pass, against SQL that no longer exercises what they claim to.
    """
    row = recording_by_id(recordings, "b05")
    tree = sqlglot.parse_one(row["sql"], read="postgres")
    ctes = list(tree.find_all(sqlglot.exp.CTE))
    assert len(ctes) >= 2, "b05 must build each side of the comparison as a CTE"

    outer_tables = {
        source.name.lower()
        for source in tree.args.get("from_", {}).find_all(sqlglot.exp.Table)
    } if tree.args.get("from_") else set()
    assert "orders" not in outer_tables, (
        "b05's reads of orders must be inside the CTE bodies, not the outer scope"
    )


def test_the_prompt_asks_for_ctes_on_comparative_questions() -> None:
    """The guidance and the recordings have to tell the same story.

    If the comparative guidance were removed, b05's recorded SQL would no longer be
    what this prompt would produce, and the fixture set would be describing a service
    that no longer exists.
    """
    assert prompt_module.is_comparative("Compare my monthly order totals to last year")
    assert not prompt_module.is_comparative("How many orders did we take last month?")
    # Whitespace-normalised: the guidance is wrapped prose, so the phrase spans a line
    # break. Asserting on the raw string would fail for a reformat that changed nothing.
    normalised = " ".join(prompt_module.COMPARATIVE_GUIDANCE.split())
    assert "common table expression" in normalised


def test_every_benign_recording_parses_as_one_statement(recordings) -> None:
    """Benign SQL must be legal input to the policy; attacks need not be."""
    for row in recordings:
        if row["kind"] != "benign":
            continue
        statements = sqlglot.parse(row["sql"], read="postgres")
        assert len(statements) == 1, row["id"]


# ---------------------------------------------------------------------------
# The adversarial corpus
# ---------------------------------------------------------------------------


def test_every_attack_case_has_a_recording(attack_cases, recordings) -> None:
    """The corpus references recordings by id; a dangling id is a test of nothing."""
    known = {row["id"] for row in recordings}
    dangling = [case["id"] for case in attack_cases if case["id"] not in known]
    assert not dangling, f"attack cases reference unknown recordings: {dangling}"


def test_every_attack_recording_is_in_the_corpus(attack_cases, recordings) -> None:
    """And the reverse: an attack recording nobody asserts on is dead weight."""
    asserted = {case["id"] for case in attack_cases}
    unasserted = [
        row["id"] for row in recordings if row["kind"] == "attack" and row["id"] not in asserted
    ]
    assert not unasserted, f"attack recordings with no declared expectation: {unasserted}"


def test_the_corpus_covers_both_outcomes(attack_cases) -> None:
    """A corpus that only expects refusals is satisfied by refusing everything.

    The allowed case is the control, and this asserts it has not been quietly dropped.
    """
    expectations = {case["expect"] for case in attack_cases}
    assert expectations == {"scoped", "refused", "allowed"}
    assert sum(1 for case in attack_cases if case["expect"] == "allowed") == 1


@pytest.mark.parametrize(
    "case_id",
    [json.loads(line)["id"] for line in open("attack/prompts.jsonl", encoding="utf-8")],
)
def test_the_policy_matches_the_declared_expectation(case_id, attack_cases, recordings) -> None:
    """Each adversarial case does what the corpus says it does.

    Parametrised one test per case so a failure names the shape that broke rather than
    reporting "the security test failed".
    """
    case = next(c for c in attack_cases if c["id"] == case_id)
    row = recording_by_id(recordings, case_id)

    try:
        result = enforce_tenant_scope(row["sql"])
    except PolicyError:
        actual = "refused"
    else:
        actual = "scoped" if result.predicates_added else "allowed"

    assert actual == case["expect"], (
        f"{case_id} ({case['probes']}) expected {case['expect']}, got {actual}. {case['why']}"
    )
