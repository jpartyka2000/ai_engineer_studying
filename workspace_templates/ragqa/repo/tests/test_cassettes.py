"""The fixture set, the evaluation set and the code must agree.

Three artefacts have to stay in step: the recording transcript, the cassettes derived
from it, and the labelled evaluation set. They are separate files on purpose -- what the
model said and what the right answer is are different claims -- and separate files drift.

**What does *not* invalidate a cassette here, and why that was a deliberate choice.**
Keys are ``sha256(model | system | question)``. The corpus is not in the key, so editing
a document, re-chunking it or changing the ranking leaves every cassette resolving. That
is the whole reason retrieval defects in this codebase produce *worse answers* rather
than "no recording found". The system prompt **is** in the key, so rewording it
invalidates all of them at once -- which is what the first test here catches.
"""

from __future__ import annotations

import pytest

from ragqa.config import MODEL
from ragqa.llm.recorded_client import CassetteMissError, cassette_key
from ragqa.rag.prompt_builder import SYSTEM_PROMPT
from tests.conftest import question_by_id


def test_every_recording_resolves_to_a_cassette(recordings, client) -> None:
    """The join that matters: what was recorded is what the service will look up.

    Computed through the real system prompt, not through the generator script, so an
    edit to the prompt fails here rather than at request time.
    """
    missing = [
        f"{row['id']} ({row['question'][:40]})"
        for row in recordings
        if not (
            client.cassette_dir
            / f"{cassette_key(model=MODEL, system=SYSTEM_PROMPT, question=row['question'])}.json"
        ).is_file()
    ]
    assert not missing, (
        f"{len(missing)} recording(s) have no cassette: {missing[:5]}. "
        "The system prompt changed; re-run `make cassettes`."
    )


def test_there_are_no_orphan_cassettes(recordings, client) -> None:
    """A cassette no question can reach is an answer nobody can review."""
    expected = {
        cassette_key(model=MODEL, system=SYSTEM_PROMPT, question=row["question"])
        for row in recordings
    }
    assert set(client.keys()) == expected


def test_every_cassette_round_trips(recordings, client) -> None:
    """Fetching through the client returns what the transcript authored."""
    for row in recordings:
        generation = client.generate(system=SYSTEM_PROMPT, question=row["question"])
        assert generation.answer == row["answer"], row["id"]
        assert list(generation.citations) == list(row["citations"]), row["id"]


def test_a_miss_is_an_error_not_a_fallback(client) -> None:
    """There is no network path out of this service, and a miss must prove it."""
    with pytest.raises(CassetteMissError, match="no cassette"):
        client.generate(system=SYSTEM_PROMPT, question="a question nobody ever recorded")


def test_the_corpus_is_not_part_of_the_key(client, recordings) -> None:
    """**The design decision, asserted.**

    A cassette key depends on the model, the system prompt and the question -- and not on
    the retrieved passages. If it did depend on them, every retrieval change would be a
    cassette miss, and a retrieval bug would surface as "no recording found" instead of
    as the worse answer it actually is.
    """
    question = recordings[0]["question"]
    key = cassette_key(model=MODEL, system=SYSTEM_PROMPT, question=question)
    assert cassette_key(model=MODEL, system=SYSTEM_PROMPT, question=question) == key
    # A different system prompt must move it; nothing about the corpus can.
    assert cassette_key(model=MODEL, system="different", question=question) != key


# ---------------------------------------------------------------------------
# The evaluation set
# ---------------------------------------------------------------------------


def test_every_answerable_question_has_a_recording(eval_questions, recordings) -> None:
    """An answerable question with no recording would raise mid-evaluation."""
    recorded = {row["id"] for row in recordings}
    missing = [
        row["id"] for row in eval_questions if row["answerable"] and row["id"] not in recorded
    ]
    assert not missing, f"answerable questions with no recording: {missing}"


def test_no_unanswerable_question_has_a_recording(eval_questions, recordings) -> None:
    """A recording for a question the system must refuse is a trap.

    It would never be reached while the router works, and would silently start being
    served the moment the router broke -- turning a refusal regression into a plausible
    answer instead of a visible failure.
    """
    recorded = {row["id"] for row in recordings}
    leaked = [
        row["id"] for row in eval_questions if not row["answerable"] and row["id"] in recorded
    ]
    assert not leaked, f"unanswerable questions with a recording: {leaked}"


def test_the_gold_answer_matches_the_recording(eval_questions, recordings) -> None:
    """At baseline the system is expected to be right, so these must be identical.

    They are authored in separate files because they are different claims -- one is what
    the model said, the other is what is correct -- and this test is what stops the two
    drifting into a baseline that is mysteriously below 1.0.
    """
    for row in eval_questions:
        if not row["answerable"]:
            continue
        recording = question_by_id(recordings, row["id"])
        assert recording["answer"] == row["gold_answer"], row["id"]


def test_the_question_text_matches_between_the_two_files(eval_questions, recordings) -> None:
    """The question is the cassette key, so a stray edit in one file is a miss."""
    for row in eval_questions:
        if not row["answerable"]:
            continue
        assert question_by_id(recordings, row["id"])["question"] == row["question"], row["id"]


def test_the_evaluation_set_is_imbalanced_on_purpose(eval_questions) -> None:
    """**The property the refusal metric is designed around.**

    Far more answerable questions than unanswerable ones, because that is the ratio
    people actually ask in. It is also what makes plain accuracy misleading and balanced
    accuracy necessary -- see ``tests/test_metrics.py``.
    """
    answerable = sum(1 for row in eval_questions if row["answerable"])
    unanswerable = sum(1 for row in eval_questions if not row["answerable"])
    assert answerable == 27
    assert unanswerable == 7
    assert answerable > 3 * unanswerable


def test_gold_citations_name_real_chunks(eval_questions, index) -> None:
    """A gold citation pointing at a chunk id that does not exist would make citation
    recall unreachable, and the failure would look like a retrieval problem."""
    for row in eval_questions:
        for chunk_id in row.get("gold_citations", []):
            assert index.get(chunk_id) is not None, f"{row['id']} cites unknown {chunk_id}"
