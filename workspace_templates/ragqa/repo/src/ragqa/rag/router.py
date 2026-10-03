"""Deciding whether we can answer at all.

The most valuable thing a retrieval-augmented assistant does is **refuse**. A system that
answers everything is worse than useless on the questions it has no basis for, because a
fluent wrong answer about notice periods is acted on, and nothing about it looks wrong.

So this module decides, before the model is called at all, whether the retrieved passages
are a basis for an answer. Two independent signals have to agree, and the reason is
measured rather than assumed.

**Why not the similarity score alone.** The vector space is hashed, so unrelated terms
share dimensions and manufacture similarity. Measured on this corpus: out-of-corpus
questions reach **0.181** cosine while genuine questions go as low as **0.148**. The
distributions overlap, so there is no threshold on this number that separates "we have an
answer" from "we do not" -- any choice either answers nonsense or refuses real questions.

**Why not coverage alone.** Coverage asks whether the question's own words appear in the
passage. That is collision-free, but it is also blind to ranking: a chunk can contain a
question's rare term in a completely unrelated sentence.

**Together they separate cleanly.** On the same measurement, out-of-corpus questions score
0.000 coverage apart from one that happens to reuse common corpus vocabulary, and genuine
questions sit well above the threshold. Requiring both is what makes refusal reliable.

A refusal is **not an error**. It is a correct answer to a question this corpus cannot
support, it is scored as such by the eval harness, and it is the behaviour most of the
value here depends on.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ragqa.rag.retriever import Retrieved

#: Minimum cosine similarity for the best passage. Deliberately permissive: this is the
#: weaker of the two signals and is here to catch the case where nothing ranked at all,
#: not to be the decision.
MIN_SCORE = 0.12

#: Minimum IDF-weighted lexical coverage for the best passage. This is the decisive
#: signal. Measured: out-of-corpus questions sit at or near zero.
MIN_COVERAGE = 0.30

#: What the service says when it will not answer. A fixed string, because the eval
#: harness scores refusal correctness by recognising it, and a model-authored apology
#: that varies by question could not be scored at all.
REFUSAL_TEXT = (
    "I don't have anything in the knowledge base that answers that. "
    "Try the service desk, or rephrase using the wording you would expect the "
    "handbook to use."
)


class Verdict(StrEnum):
    """What the router decided, and on what grounds."""

    ANSWER = "answer"
    NO_MATCH = "no_match"
    WEAK_MATCH = "weak_match"


@dataclass(frozen=True)
class Decision:
    """The routing decision for one question.

    Attributes:
        verdict: Whether to answer, and if not, why not.
        top_score: Cosine similarity of the best passage, or 0.0 if none.
        top_coverage: Lexical coverage of the best passage, or 0.0 if none.
        reason: One line, suitable for a log or an audit record.
    """

    verdict: Verdict
    top_score: float
    top_coverage: float
    reason: str

    @property
    def should_answer(self) -> bool:
        """Whether the pipeline should proceed to generation."""
        return self.verdict is Verdict.ANSWER


def decide(
    retrieved: list[Retrieved],
    *,
    min_score: float = MIN_SCORE,
    min_coverage: float = MIN_COVERAGE,
) -> Decision:
    """Decide whether the retrieved passages support an answer.

    Args:
        retrieved: Hits from the retriever, best first.
        min_score: Minimum cosine similarity for the best hit.
        min_coverage: Minimum lexical coverage for the best hit.

    Returns:
        A :class:`Decision`. Both thresholds must be met; see the module docstring for
        why either alone is insufficient.
    """
    if not retrieved:
        return Decision(
            verdict=Verdict.NO_MATCH,
            top_score=0.0,
            top_coverage=0.0,
            reason="nothing retrieved",
        )

    best = retrieved[0]
    if best.score < min_score:
        return Decision(
            verdict=Verdict.NO_MATCH,
            top_score=best.score,
            top_coverage=best.coverage,
            reason=f"best similarity {best.score:.3f} below {min_score:.2f}",
        )
    if best.coverage < min_coverage:
        return Decision(
            verdict=Verdict.WEAK_MATCH,
            top_score=best.score,
            top_coverage=best.coverage,
            reason=(
                f"best passage ranked ({best.score:.3f}) but covers only "
                f"{best.coverage:.3f} of the question's terms, below {min_coverage:.2f}"
            ),
        )
    return Decision(
        verdict=Verdict.ANSWER,
        top_score=best.score,
        top_coverage=best.coverage,
        reason=f"similarity {best.score:.3f}, coverage {best.coverage:.3f}",
    )
