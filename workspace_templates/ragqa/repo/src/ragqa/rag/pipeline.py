"""Question in, grounded answer or an honest refusal out.

The order is the point, and every step can stop the one after it:

1. **Retrieve** the closest passages.
2. **Screen** them, withholding anything carrying instruction-shaped text.
3. **Route** on what survived -- if the remaining passages are not a basis for an answer,
   refuse here and never call the model at all.
4. **Assemble** the prompt from the passages that fit the budget.
5. **Generate**.
6. **Validate** the citations against what was actually shown, dropping any the model
   invented.

Two consequences worth stating because they are easy to get backwards.

**Screening happens before routing.** If the only passage that ranked was a tampered one,
withholding it must leave the router with nothing, so the system refuses. Screening
afterwards would mean the router approved an answer on the strength of a passage that was
then removed, and the model would answer from whatever was left.

**Refusing is a successful outcome.** It is not an error, it is not a fallback, and it is
scored as correct behaviour by :mod:`ragqa.eval.metrics` whenever the question was not
answerable from the corpus. Most of the value of a system like this lives in step 3.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ragqa.llm.recorded_client import CassetteMissError, RecordedClient
from ragqa.rag import guardrails, prompt_builder, router
from ragqa.rag.retriever import DEFAULT_TOP_K, Index
from ragqa.rag.router import REFUSAL_TEXT, Decision

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Answer:
    """What the pipeline produced for one question.

    Attributes:
        question: As asked.
        text: The answer, or the refusal text.
        refused: Whether the system declined to answer.
        citations: Chunk ids that survived validation.
        fabricated: Chunk ids the model cited that were never shown. Dropped from
            ``citations`` and kept here, because a model inventing sources is worth
            counting rather than merely discarding.
        retrieved: Every chunk id retrieved, before screening.
        shown: Chunk ids actually placed in the prompt.
        quarantined: Chunk ids withheld by the guardrails, with reasons.
        dropped: Chunk ids removed to fit the context budget.
        decision: The router's verdict and the numbers behind it.
    """

    question: str
    text: str
    refused: bool
    citations: tuple[str, ...] = ()
    fabricated: tuple[str, ...] = ()
    retrieved: tuple[str, ...] = ()
    shown: tuple[str, ...] = ()
    quarantined: tuple[guardrails.Quarantined, ...] = ()
    dropped: tuple[str, ...] = ()
    decision: Decision | None = field(default=None)

    def as_dict(self) -> dict[str, Any]:
        """Return the answer as a JSON-serialisable dict."""
        return {
            "question": self.question,
            "answer": self.text,
            "refused": self.refused,
            "citations": list(self.citations),
            "fabricated_citations": list(self.fabricated),
            "retrieved": list(self.retrieved),
            "shown": list(self.shown),
            "quarantined": [
                {"chunk_id": q.chunk_id, "labels": list(q.labels)} for q in self.quarantined
            ],
            "dropped_for_budget": list(self.dropped),
            "routing": (
                {
                    "verdict": str(self.decision.verdict),
                    "top_score": self.decision.top_score,
                    "top_coverage": self.decision.top_coverage,
                    "reason": self.decision.reason,
                }
                if self.decision
                else None
            ),
        }


def answer_question(
    question: str,
    *,
    index: Index,
    client: RecordedClient,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = router.MIN_SCORE,
    min_coverage: float = router.MIN_COVERAGE,
    budget: int = prompt_builder.CONTEXT_BUDGET_CHARS,
) -> Answer:
    """Answer one question against the corpus.

    Args:
        question: The user's question.
        index: The built index.
        client: The recorded model client.
        top_k: Passages to retrieve.
        min_score: Router similarity threshold.
        min_coverage: Router lexical-coverage threshold.
        budget: Character budget for assembled context.

    Returns:
        An :class:`Answer`. A refusal is a normal return value, not an exception.

    Raises:
        CassetteMissError: If the router decided to answer but nothing is recorded for
            this question. Deliberately propagated: it means the fixture set and the
            evaluation set have drifted apart, which is a problem with the repository
            rather than with the question.
    """
    retrieved = index.search(question, top_k=top_k)
    screened = guardrails.screen(
        retrieved, tainted_documents=index.tainted_documents
    )
    decision = router.decide(
        screened.safe, min_score=min_score, min_coverage=min_coverage
    )

    retrieved_ids = tuple(hit.chunk.chunk_id for hit in retrieved)
    quarantined = tuple(screened.quarantined)

    if not decision.should_answer:
        logger.info("refused %r: %s", question[:60], decision.reason)
        return Answer(
            question=question,
            text=REFUSAL_TEXT,
            refused=True,
            retrieved=retrieved_ids,
            quarantined=quarantined,
            decision=decision,
        )

    prompt = prompt_builder.build(question, screened.safe, budget=budget)
    generation = client.generate(system=prompt.system, question=question)
    check = guardrails.validate_citations(list(generation.citations), list(prompt.shown))

    return Answer(
        question=question,
        text=generation.answer,
        refused=False,
        citations=check.supported,
        fabricated=check.fabricated,
        retrieved=retrieved_ids,
        shown=prompt.shown,
        quarantined=quarantined,
        dropped=prompt.dropped,
        decision=decision,
    )
