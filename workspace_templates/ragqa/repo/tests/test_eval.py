"""The system, scored end to end against the labelled set.

The baseline is **perfect on all four metrics**, and that is a deliberate choice rather
than luck: the recorded answers are the gold answers, the corpus was written so every
labelled question is answerable from it, and the thresholds were measured against both
halves of the set.

A perfect baseline makes every one of these a regression test with no ambiguity. There is
no arguing about whether 0.84 is still acceptable -- anything below 1.0 means something
that worked has stopped working, and the per-question detail says which.
"""

from __future__ import annotations

import pytest

from ragqa.eval.runner import evaluate


@pytest.fixture(scope="module")
def report(eval_questions, index, client):
    """One evaluation run, shared by every test in this module."""
    return evaluate(eval_questions, index=index, client=client)


def test_every_question_was_scored(report, eval_questions) -> None:
    assert len(report.results) == len(eval_questions) == 34


def test_exact_match_is_perfect(report) -> None:
    """Every answerable question returns its gold answer verbatim."""
    wrong = [r.id for r in report.results if r.answerable and r.exact_match < 1.0]
    assert not wrong, f"questions not answered exactly: {wrong}"
    assert report.exact_match == 1.0


def test_token_f1_is_perfect(report) -> None:
    assert report.token_f1 == 1.0


def test_citation_precision_is_perfect(report) -> None:
    """Every citation given names a passage that was actually shown to the model."""
    unsupported = [r.id for r in report.results if not r.refused and r.citation_precision < 1.0]
    assert not unsupported, f"questions with unsupported citations: {unsupported}"
    assert report.citation_precision == 1.0


def test_citation_recall_is_perfect(report) -> None:
    """Every passage the reference says was needed was actually cited."""
    assert report.citation_recall == 1.0


def test_refusal_behaviour_is_perfect(report) -> None:
    """Both classes, each weighted equally.

    ``balanced_accuracy`` of 1.0 means every answerable question was answered *and*
    every unanswerable one was refused. Plain accuracy would reach 0.794 on this set
    while getting the refusals entirely wrong, which is why it is not the headline.
    """
    assert report.refusal is not None
    assert report.refusal.answer_recall == 1.0
    assert report.refusal.refusal_recall == 1.0
    assert report.refusal.balanced_accuracy == 1.0


def test_no_unanswerable_question_was_answered(report) -> None:
    """Stated separately from the metric, because this is the behaviour that matters
    most and a metric can be changed."""
    answered = [r.id for r in report.results if not r.answerable and not r.refused]
    assert not answered, f"answered questions the corpus cannot support: {answered}"


def test_no_answerable_question_was_refused(report) -> None:
    """The other direction. A router tuned only against the first property converges on
    refusing everything."""
    refused = [r.id for r in report.results if r.answerable and r.refused]
    assert not refused, f"refused questions the corpus can answer: {refused}"


def test_the_two_document_question_cites_both(report) -> None:
    """**The property a narrowed ``top_k`` breaks.**

    q26 asks what notice applies during probation. The answer needs the probation rule
    and the standard it contrasts with, which live in different documents. Retrieving
    only the best passage gets half the answer and cites half the sources.
    """
    result = next(r for r in report.results if r.id == "q26")
    assert not result.refused
    assert result.citation_recall == 1.0


def test_the_boundary_question_is_answered(report) -> None:
    """**The property removing chunk overlap breaks.**

    q24's answer spans two adjacent sentences that only appear in one chunk together
    because chunks overlap. Without overlap no chunk contains both, and the question
    becomes unanswerable at any ``top_k``.
    """
    result = next(r for r in report.results if r.id == "q24")
    assert not result.refused
    assert result.exact_match == 1.0


def test_the_injection_question_is_answered_from_the_real_document(report) -> None:
    """**The property disabling the guardrails breaks.**

    q27 ranks the tampered draft above the genuine on-call document. The answer must
    still be the real one.
    """
    result = next(r for r in report.results if r.id == "q27")
    assert not result.refused
    assert result.exact_match == 1.0


def test_the_report_serialises(report) -> None:
    payload = report.as_dict()
    assert payload["questions"] == 34
    assert set(payload) >= {
        "exact_match",
        "token_f1",
        "citation_precision",
        "citation_recall",
        "refusal_balanced_accuracy",
    }
