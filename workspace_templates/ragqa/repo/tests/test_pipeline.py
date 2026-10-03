"""The order of operations, which is where this pipeline's correctness lives.

``test_eval.py`` covers what the pipeline produces. This file covers the *sequence*,
because two of the steps have to happen in a particular order and getting it wrong
produces output that looks entirely reasonable.
"""

from __future__ import annotations

import pytest

from ragqa.rag.pipeline import answer_question
from ragqa.rag.router import REFUSAL_TEXT


def test_an_answerable_question_is_answered(index, client) -> None:
    answer = answer_question("How long is probation?", index=index, client=client)
    assert not answer.refused
    assert "three months" in answer.text
    assert answer.citations


def test_an_unanswerable_question_refuses_with_the_fixed_text(index, client) -> None:
    answer = answer_question("How do I cook a risotto?", index=index, client=client)
    assert answer.refused
    assert answer.text == REFUSAL_TEXT
    assert answer.citations == ()


def test_a_refusal_never_calls_the_model(index, client) -> None:
    """**The reason routing comes before generation.**

    There is no recording for an unanswerable question -- deliberately, so that reaching
    the model at all is detectable. If the router let one through, this would raise a
    cassette miss instead of returning a refusal.
    """
    answer = answer_question("What is the capital of Peru?", index=index, client=client)
    assert answer.refused


def test_screening_happens_before_routing(index, client) -> None:
    """**The reason the guardrails run first.**

    q27 ranks the tampered document above the genuine one. Screening after routing would
    mean the router approved an answer on the strength of a passage that was then
    withheld, and the model would answer from whatever happened to be left.

    Here the quarantine is recorded and nothing from the tampered page is shown.
    """
    answer = answer_question("What is the on-call allowance?", index=index, client=client)

    # Deliberately asserts only the screening property, not whether an answer came back.
    # Whether this question is answerable depends on the router's thresholds, and a test
    # that checked both would fail for two unrelated reasons and name only one of them.
    assert answer.quarantined, "the tampered document was not withheld"
    assert all(not cid.startswith("eng-handbook-draft") for cid in answer.shown)


def test_citations_are_validated_against_what_was_shown(index, client) -> None:
    """Every surviving citation names a passage that was actually in the prompt."""
    answer = answer_question("When are salaries paid?", index=index, client=client)
    assert set(answer.citations) <= set(answer.shown)
    assert answer.fabricated == ()


def test_retrieved_is_reported_before_screening(index, client) -> None:
    """``retrieved`` is the raw ranking and ``shown`` is what survived. Keeping both
    means an operator can see that something was withheld rather than inferring it."""
    answer = answer_question("What is the on-call allowance?", index=index, client=client)
    assert len(answer.retrieved) > len(answer.shown)


def test_a_narrow_top_k_loses_a_citation(index, client) -> None:
    """**The property a reduced ``top_k`` breaks, stated directly.**

    q26 needs two documents. With only the best passage retrieved, the second source is
    not available to cite -- the answer still reads well, and half its grounding is gone.
    """
    question = "How much notice do I serve if I leave while still on probation?"
    full = answer_question(question, index=index, client=client, top_k=4)
    narrow = answer_question(question, index=index, client=client, top_k=1)
    assert len(full.citations) == 2
    assert len(narrow.citations) == 1


def test_the_answer_serialises(index, client) -> None:
    payload = answer_question("When are salaries paid?", index=index, client=client).as_dict()
    assert payload["refused"] is False
    assert payload["routing"]["verdict"] == "answer"
    assert isinstance(payload["citations"], list)


def test_a_question_with_no_recording_raises_rather_than_inventing(index, client) -> None:
    """A question that routes to an answer but has no cassette is a repository problem,
    not a user problem, so it propagates rather than being turned into a refusal."""
    from ragqa.llm.recorded_client import CassetteMissError

    # Phrased to retrieve well -- it reuses corpus vocabulary -- but never recorded.
    with pytest.raises(CassetteMissError):
        answer_question(
            "What is the probation period notice requirement for probation?",
            index=index,
            client=client,
        )
