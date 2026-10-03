"""Running the evaluation set and reporting the four numbers.

Every question in ``eval/questions.jsonl`` goes through the **real pipeline** -- the same
retriever, guardrails, router and prompt assembly the API uses. Scoring a shortcut would
measure the shortcut.

**Refusals are scored, not skipped.** An answerable question that was refused scores zero
on exact match and F1, which is correct: the user did not get their answer. An
unanswerable question that was refused scores as a correct refusal and is excluded from
the answer-quality averages, which is also correct -- there was no answer to judge, and
averaging a zero in would make a well-behaved system look worse the more unanswerable
questions it was tested on.

That asymmetry is the one piece of arithmetic here worth reading twice, because getting
it backwards produces a report that rewards exactly the wrong behaviour.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ragqa.eval.metrics import (
    RefusalScore,
    citation_metrics,
    exact_match,
    refusal_metrics,
    token_f1,
)
from ragqa.llm.recorded_client import RecordedClient
from ragqa.rag.pipeline import answer_question
from ragqa.rag.retriever import DEFAULT_TOP_K, Index

logger = logging.getLogger(__name__)


@dataclass
class QuestionResult:
    """What one evaluation question produced.

    Attributes:
        id: Question id.
        question: As asked.
        answerable: Whether the reference says the corpus can answer it.
        refused: Whether the system refused.
        exact_match: 1.0 or 0.0. Zero for a refused answerable question.
        token_f1: Partial credit in ``[0, 1]``.
        citation_precision: Of the citations given, the fraction actually retrieved.
        citation_recall: Of the citations expected, the fraction given.
        answer: The system's answer text.
    """

    id: str
    question: str
    answerable: bool
    refused: bool
    exact_match: float = 0.0
    token_f1: float = 0.0
    citation_precision: float = 0.0
    citation_recall: float = 0.0
    answer: str = ""


@dataclass
class EvalReport:
    """The full evaluation outcome.

    Attributes:
        results: Per-question detail.
        exact_match: Mean exact match over **answerable** questions.
        token_f1: Mean token F1 over answerable questions.
        citation_precision: Mean precision over answered questions.
        citation_recall: Mean recall over answered questions.
        refusal: The refusal breakdown, whose headline is balanced accuracy.
    """

    results: list[QuestionResult] = field(default_factory=list)
    exact_match: float = 0.0
    token_f1: float = 0.0
    citation_precision: float = 0.0
    citation_recall: float = 0.0
    refusal: RefusalScore | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return the headline numbers as a JSON-serialisable dict."""
        return {
            "questions": len(self.results),
            "exact_match": round(self.exact_match, 4),
            "token_f1": round(self.token_f1, 4),
            "citation_precision": round(self.citation_precision, 4),
            "citation_recall": round(self.citation_recall, 4),
            "refusal_balanced_accuracy": (
                round(self.refusal.balanced_accuracy, 4) if self.refusal else 0.0
            ),
            "refusal_plain_accuracy": (
                round(self.refusal.plain_accuracy, 4) if self.refusal else 0.0
            ),
            "answer_recall": round(self.refusal.answer_recall, 4) if self.refusal else 0.0,
            "refusal_recall": round(self.refusal.refusal_recall, 4) if self.refusal else 0.0,
        }


def evaluate(
    questions: list[dict],
    *,
    index: Index,
    client: RecordedClient,
    top_k: int = DEFAULT_TOP_K,
    **pipeline_kwargs,
) -> EvalReport:
    """Run the evaluation set through the pipeline and score it.

    Args:
        questions: Rows from ``eval/questions.jsonl``.
        index: The built index.
        client: The recorded model client.
        top_k: Passages to retrieve per question.
        **pipeline_kwargs: Forwarded to the pipeline, so a caller can sweep thresholds.

    Returns:
        An :class:`EvalReport`.
    """
    results: list[QuestionResult] = []
    decisions: list[tuple[bool, bool]] = []

    for row in questions:
        answerable = bool(row["answerable"])
        answer = answer_question(
            row["question"], index=index, client=client, top_k=top_k, **pipeline_kwargs
        )
        decisions.append((answerable, not answer.refused))

        result = QuestionResult(
            id=row["id"],
            question=row["question"],
            answerable=answerable,
            refused=answer.refused,
            answer=answer.text,
        )

        if answerable:
            # A refusal here scores zero rather than being skipped: the asker did not
            # get their answer, and a metric that looked away would rate a system that
            # refuses everything as perfect on the questions it deigned to attempt.
            predicted = "" if answer.refused else answer.text
            result.exact_match = exact_match(predicted, row["gold_answer"])
            result.token_f1 = token_f1(predicted, row["gold_answer"])

        if not answer.refused:
            citations = citation_metrics(
                cited=list(answer.citations) + list(answer.fabricated),
                gold=row.get("gold_citations", []),
                retrieved=list(answer.shown),
            )
            result.citation_precision = citations.precision
            result.citation_recall = citations.recall

        results.append(result)

    answerable_results = [r for r in results if r.answerable]
    answered_results = [r for r in results if not r.refused]

    def mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    return EvalReport(
        results=results,
        exact_match=mean([r.exact_match for r in answerable_results]),
        token_f1=mean([r.token_f1 for r in answerable_results]),
        citation_precision=mean([r.citation_precision for r in answered_results]),
        citation_recall=mean([r.citation_recall for r in answered_results]),
        refusal=refusal_metrics(decisions),
    )
