"""Retrieval: ranking, the two signals, and the benchmark.

The numbers in this file were measured against this corpus and are pinned so a change to
chunking, weighting or dimensionality shows up as a named failure rather than as a
slightly different answer somewhere downstream.
"""

from __future__ import annotations

import pytest

from ragqa.rag.embedding import DIMENSIONS, Vectorizer, cosine_similarity, dot, tokenize
from ragqa.rag.retriever import Index

#: Benchmark: question -> the document that answers it. Every entry was checked by hand
#: against the corpus, so a failure here is a retrieval regression and not a disagreement
#: about what the right answer is.
BENCHMARK: tuple[tuple[str, str], ...] = (
    ("How many days of annual leave do I get?", "hr-leave"),
    ("What is the notice period for a senior engineer?", "hr-notice"),
    ("How long is probation?", "hr-probation"),
    ("How much paid parental leave do primary caregivers get?", "hr-parental"),
    ("When do I need a fit note?", "hr-sickness"),
    ("How many days a week can I work remotely?", "hr-remote"),
    ("How do I get remote access to internal systems?", "it-vpn"),
    ("When are laptops replaced?", "it-laptop"),
    ("How long must a password be?", "it-password"),
    ("What hours is the service desk staffed?", "it-servicedesk"),
    ("How do I request non-standard software?", "it-software"),
    ("How long do I have to submit an expense claim?", "fin-expenses"),
    ("What is the hotel spend cap in London?", "fin-travel"),
    ("When is a purchase order required?", "fin-procurement"),
    ("When are salaries paid?", "fin-payroll"),
    ("Who do I tell about a security incident?", "sec-incident"),
    ("How do I report a phishing email?", "sec-phishing"),
    ("What are the data classification levels?", "sec-data"),
    ("How often is production access reviewed?", "sec-access"),
    ("When are deployments frozen?", "eng-deploy"),
    ("How many approvals does a payment change need?", "eng-review"),
    ("How often are incident status updates posted?", "eng-incident"),
    ("How far in advance must I request a holiday longer than ten days?", "hr-leave"),
    ("How often are critical suppliers reviewed?", "pol-supplier"),
)


def test_tokenize_drops_stop_words_and_short_tokens() -> None:
    assert tokenize("What is the notice period?") == ["notice", "period"]


def test_the_vectoriser_must_be_fitted() -> None:
    """An unfitted vectoriser weights every term identically -- a plausible-looking
    vector and a quietly wrong ranking -- so it raises rather than guessing."""
    with pytest.raises(RuntimeError, match="not fitted"):
        Vectorizer().transform("anything")


def test_fitting_on_nothing_is_an_error() -> None:
    with pytest.raises(ValueError, match="empty corpus"):
        Vectorizer.fit([])


def test_a_rare_term_outweighs_a_common_one(index: Index) -> None:
    """IDF is what stops "days" -- which is in half the handbook -- drowning out the
    word that made a question a question."""
    assert index.vectorizer.weight("probation") > index.vectorizer.weight("days")


def test_cosine_is_not_a_dot_product() -> None:
    """**The property length-biased ranking breaks.**

    The same direction at two magnitudes is the same *content*: a long passage and a
    short one that are about exactly the same thing should score equally. Cosine says so.
    The dot product says the long one is three times better.
    """
    short = [1.0, 1.0, 0.0]
    long_version = [3.0, 3.0, 0.0]
    query = [1.0, 1.0, 0.0]

    assert cosine_similarity(query, short) == pytest.approx(1.0)
    assert cosine_similarity(query, long_version) == pytest.approx(1.0)
    assert dot(query, long_version) == 3 * dot(query, short)


def test_an_all_zero_vector_scores_zero_rather_than_dividing() -> None:
    """Text made only of stop words embeds to zeros. That is a real input."""
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_the_index_covers_the_corpus(index: Index, documents: list[dict]) -> None:
    assert len({chunk.doc_id for chunk in index.chunks}) == len(documents)
    assert index.vectorizer.dimensions == DIMENSIONS


@pytest.mark.parametrize("question,expected_doc", BENCHMARK)
def test_the_benchmark_question_retrieves_its_document(
    index: Index, question: str, expected_doc: str
) -> None:
    """One test per question, so a retrieval regression names the question that broke.

    This is the suite's floor: if these stop passing, every downstream metric is
    measuring something other than what it claims to.
    """
    top = index.search(question)[0]
    assert top.chunk.doc_id == expected_doc, (
        f"expected {expected_doc}, got {top.chunk.chunk_id} at score {top.score:.3f}"
    )


def test_results_are_ordered_by_score(index: Index) -> None:
    hits = index.search("How long is probation?")
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_ties_break_deterministically(index: Index) -> None:
    """Two runs must return the same order, or a citation test flakes for no reason."""
    assert [h.chunk.chunk_id for h in index.search("probation")] == [
        h.chunk.chunk_id for h in index.search("probation")
    ]


def test_coverage_is_zero_for_a_question_the_corpus_cannot_answer(index: Index) -> None:
    """**The collision-free signal.**

    A hashed vector space manufactures similarity: unrelated terms share dimensions and
    an out-of-corpus question can score as high as a real one. Coverage compares strings
    rather than hashes, so it cannot be fooled the same way.
    """
    for question in ("How do I cook a risotto?", "What is the capital of Peru?"):
        best = index.search(question)[0]
        assert best.coverage == 0.0, f"{question!r} covered {best.coverage:.3f}"


def test_coverage_is_high_for_a_question_the_corpus_answers(index: Index) -> None:
    best = index.search("How long is probation?")[0]
    assert best.coverage > 0.3


def test_top_k_must_be_positive(index: Index) -> None:
    with pytest.raises(ValueError, match="top_k"):
        index.search("anything", top_k=0)
