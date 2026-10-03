"""The four numbers this system is judged on.

Every one is a pure function over strings and ids. No model, no database, no corpus --
which is what lets each be tested against a constant worked out by hand in the test's own
docstring, and what makes it possible to argue about whether a metric is *right* rather
than only about whether it ran.

Each is also chosen against a specific way of being fooled:

:func:`exact_match`
    Strict and unforgiving. Normalised so that punctuation and articles do not decide it,
    because "25 days." and "25 days" are the same answer.

:func:`token_f1`
    Partial credit, as the **harmonic mean of precision and recall**. Recall alone would
    reward padding: an answer that recites the whole handbook contains every gold token
    and would score 1.0. Precision alone would reward terseness to the point of
    uselessness. Only the pair resists both.

:func:`citation_metrics`
    Precision against what was **actually retrieved and shown**, not against what exists
    in the corpus. A citation to a real document the system never read is a fabricated
    citation, and it is the single most dangerous output here because it is the thing a
    reader uses to decide whether to trust the answer.

:func:`refusal_metrics`
    Reported as **balanced accuracy** over the two classes, never as plain accuracy. The
    evaluation set has far more answerable questions than unanswerable ones, as any real
    one does, so a system that simply answers everything scores over 80% on plain
    accuracy while being exactly as wrong as a coin toss on the question that matters.
"""

from __future__ import annotations

import re
import string
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence

from ragqa.rag.embedding import tokenize

_ARTICLES = re.compile(r"\b(a|an|the)\b")
_WHITESPACE = re.compile(r"\s+")
_PUNCTUATION = str.maketrans("", "", string.punctuation)


def normalize_answer(text: str) -> str:
    """Normalise an answer for comparison.

    Lower-cases, strips punctuation, removes articles and collapses whitespace. This is
    the standard treatment from the reading-comprehension literature and exists so that
    "The notice period is 30 days." and "notice period is 30 days" are not scored as
    different answers.

    Args:
        text: Raw answer text.

    Returns:
        The normalised form.
    """
    lowered = text.lower()
    without_punctuation = lowered.translate(_PUNCTUATION)
    without_articles = _ARTICLES.sub(" ", without_punctuation)
    return _WHITESPACE.sub(" ", without_articles).strip()


def exact_match(prediction: str, gold: str) -> float:
    """Return 1.0 if the normalised answers are identical, else 0.0.

    Args:
        prediction: The system's answer.
        gold: The reference answer.

    Returns:
        1.0 or 0.0.
    """
    return 1.0 if normalize_answer(prediction) == normalize_answer(gold) else 0.0


def token_f1(prediction: str, gold: str) -> float:
    """Return the token-level F1 of a prediction against a reference.

    Tokens come from :func:`ragqa.rag.embedding.tokenize`, so "what counts as a word" has
    one definition shared with retrieval -- a scoring change cannot silently diverge from
    a retrieval change.

    Overlap is counted as a **multiset** intersection. Using sets instead would let a
    prediction saying "days days days" match a gold answer containing "days" three times
    as fully as one that says it once, which is not the same claim.

    Args:
        prediction: The system's answer.
        gold: The reference answer.

    Returns:
        F1 in ``[0, 1]``. Two empty answers score 1.0 -- they agree -- while one empty
        and one not scores 0.0.
    """
    predicted_tokens = Counter(tokenize(normalize_answer(prediction)))
    gold_tokens = Counter(tokenize(normalize_answer(gold)))

    if not predicted_tokens and not gold_tokens:
        return 1.0
    if not predicted_tokens or not gold_tokens:
        return 0.0

    overlap = sum((predicted_tokens & gold_tokens).values())
    if overlap == 0:
        return 0.0

    precision = overlap / sum(predicted_tokens.values())
    recall = overlap / sum(gold_tokens.values())
    return 2 * precision * recall / (precision + recall)


@dataclass(frozen=True)
class CitationScore:
    """How well an answer's citations were supported.

    Attributes:
        precision: Of the chunks cited, the fraction that were actually retrieved for
            this question. A citation to something the system never read is fabricated,
            whether or not the document exists.
        recall: Of the chunks that should have been cited, the fraction that were.
        cited: How many citations the answer carried.
        supported: How many of those were in the retrieved set.
        expected: How many the reference says were needed.
    """

    precision: float
    recall: float
    cited: int
    supported: int
    expected: int


def citation_metrics(
    cited: Sequence[str],
    gold: Sequence[str],
    retrieved: Iterable[str],
) -> CitationScore:
    """Score an answer's citations.

    Args:
        cited: Chunk ids the answer cited.
        gold: Chunk ids the reference says were needed.
        retrieved: Chunk ids actually retrieved and put in front of the model.

    Returns:
        A :class:`CitationScore`.

    Note:
        Precision is measured against ``retrieved``, **not** against the corpus. A
        citation naming a real document that was never retrieved is the failure mode
        worth catching: the system had no access to that text, so whatever it said about
        it was not grounded in it. Checking only that the id exists somewhere in the
        corpus would score exactly that case as correct.
    """
    cited_set = set(cited)
    gold_set = set(gold)
    retrieved_set = set(retrieved)

    supported = len(cited_set & retrieved_set)
    precision = supported / len(cited_set) if cited_set else 1.0
    recall = len(cited_set & gold_set) / len(gold_set) if gold_set else 1.0

    return CitationScore(
        precision=precision,
        recall=recall,
        cited=len(cited_set),
        supported=supported,
        expected=len(gold_set),
    )


@dataclass(frozen=True)
class RefusalScore:
    """How well the system decided whether to answer at all.

    Attributes:
        answer_recall: Of the answerable questions, the fraction actually answered.
        refusal_recall: Of the unanswerable questions, the fraction actually refused.
        balanced_accuracy: The mean of the two. **This is the headline number.**
        plain_accuracy: Correct decisions over all questions. Reported only so that the
            gap between it and the balanced figure is visible; it is not the score.
        answerable: How many questions were answerable.
        unanswerable: How many were not.
    """

    answer_recall: float
    refusal_recall: float
    balanced_accuracy: float
    plain_accuracy: float
    answerable: int
    unanswerable: int


def refusal_metrics(decisions: Sequence[tuple[bool, bool]]) -> RefusalScore:
    """Score refusal behaviour over an evaluation set.

    Args:
        decisions: ``(should_answer, did_answer)`` pairs, one per question.

    Returns:
        A :class:`RefusalScore`.

    Note:
        **Balanced accuracy, not plain accuracy.** Real evaluation sets are dominated by
        answerable questions, because that is what people ask. Plain accuracy on such a
        set is mostly a measure of how often the system answers, so a system that has
        never refused anything scores well on it and the one behaviour being measured --
        knowing when to stop -- contributes almost nothing. Averaging the two classes
        gives each equal weight regardless of how many of each the set happens to hold,
        and a never-refusing system scores exactly 0.5.
    """
    answerable = [(should, did) for should, did in decisions if should]
    unanswerable = [(should, did) for should, did in decisions if not should]

    answer_recall = (
        sum(1 for _, did in answerable if did) / len(answerable) if answerable else 1.0
    )
    refusal_recall = (
        sum(1 for _, did in unanswerable if not did) / len(unanswerable)
        if unanswerable
        else 1.0
    )
    correct = sum(1 for should, did in decisions if should == did)

    return RefusalScore(
        answer_recall=answer_recall,
        refusal_recall=refusal_recall,
        balanced_accuracy=(answer_recall + refusal_recall) / 2,
        plain_accuracy=correct / len(decisions) if decisions else 1.0,
        answerable=len(answerable),
        unanswerable=len(unanswerable),
    )
