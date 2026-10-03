"""Knowing when to stop.

The router is the only component here whose job is to produce *nothing*, and these tests
are mostly about the two thresholds having to agree. Either on its own has a documented
failure mode, and both are measured against this corpus rather than chosen.
"""

from __future__ import annotations

import pytest

from ragqa.rag.chunker import Chunk
from ragqa.rag.retriever import Index, Retrieved
from ragqa.rag.router import (
    MIN_COVERAGE,
    MIN_SCORE,
    REFUSAL_TEXT,
    Verdict,
    decide,
)

#: Questions this corpus cannot answer. Each was checked to be genuinely absent rather
#: than merely phrased unusually.
UNANSWERABLE = (
    "What is our share price today?",
    "Who won the World Cup in 1998?",
    "What is the capital of Peru?",
    "Can you write me a poem about otters?",
    "How do I cook a risotto?",
    "What were our Q3 revenue figures?",
    "What is the current headcount in the Berlin office?",
)

ANSWERABLE = (
    "How long is probation?",
    "When are salaries paid?",
    "How many days a week can I work remotely?",
    "When are deployments frozen?",
)


def hit(score: float, coverage: float) -> Retrieved:
    """Build a synthetic hit, so threshold behaviour is tested without a corpus."""
    return Retrieved(
        chunk=Chunk(chunk_id="d#0", doc_id="d", title="T", text="text", index=0),
        score=score,
        coverage=coverage,
    )


def test_nothing_retrieved_is_a_refusal() -> None:
    decision = decide([])
    assert decision.verdict is Verdict.NO_MATCH
    assert not decision.should_answer


def test_both_thresholds_must_be_met() -> None:
    """The decisive property: either signal alone can veto.

    A passage that ranks well but shares none of the question's words is a hash
    collision. A passage full of the question's words that ranked nowhere is a
    coincidence. Neither is a basis for an answer.
    """
    assert decide([hit(0.50, 0.50)]).should_answer

    weak_score = decide([hit(0.05, 0.90)])
    assert not weak_score.should_answer
    assert weak_score.verdict is Verdict.NO_MATCH

    weak_coverage = decide([hit(0.50, 0.05)])
    assert not weak_coverage.should_answer
    assert weak_coverage.verdict is Verdict.WEAK_MATCH


def test_the_two_refusals_are_distinguishable() -> None:
    """"Nothing ranked" and "something ranked but is not about this" are different
    problems -- one is a gap in the corpus, the other is a retrieval failure -- and the
    reason string has to say which."""
    assert "below" in decide([hit(0.05, 0.90)]).reason
    assert "covers only" in decide([hit(0.50, 0.05)]).reason


def test_the_boundary_is_inclusive() -> None:
    """Exactly at both thresholds is an answer, not a refusal."""
    assert decide([hit(MIN_SCORE, MIN_COVERAGE)]).should_answer


def test_only_the_best_passage_decides() -> None:
    """Later hits cannot rescue a bad first one. If the best passage is not a basis for
    an answer, the fourth-best is not either."""
    assert not decide([hit(0.50, 0.05), hit(0.49, 0.99)]).should_answer


@pytest.mark.parametrize("question", UNANSWERABLE)
def test_an_unanswerable_question_is_refused(index: Index, question: str) -> None:
    """One test per question, so a regression names the one that started being answered.

    This is the behaviour the whole system exists for: a fluent wrong answer about
    notice periods gets acted on, and nothing about it looks wrong.
    """
    assert not decide(index.search(question)).should_answer


@pytest.mark.parametrize("question", ANSWERABLE)
def test_an_answerable_question_is_not_refused(index: Index, question: str) -> None:
    """The other half, and the reason thresholds cannot simply be raised.

    A router tuned only against unanswerable questions converges on refusing
    everything, which scores perfectly on half the evaluation set.
    """
    assert decide(index.search(question)).should_answer


def test_the_refusal_text_is_fixed() -> None:
    """The eval harness recognises a refusal by this string, and a model-authored
    apology that varied per question could not be scored at all."""
    assert "don't have anything in the knowledge base" in REFUSAL_TEXT
