"""The four metrics, each against a constant worked out by hand.

A metric is the one piece of code nobody checks, because a number always comes back and
it always looks like a score. So every expectation here is derived in its own docstring
from the tokens involved, and each metric gets at least one test for **the way it can be
fooled** rather than only for the way it works.
"""

from __future__ import annotations

from ragqa.eval.metrics import (
    citation_metrics,
    exact_match,
    normalize_answer,
    refusal_metrics,
    token_f1,
)


# ---------------------------------------------------------------------------
# exact match
# ---------------------------------------------------------------------------


def test_normalisation_ignores_case_punctuation_and_articles() -> None:
    assert normalize_answer("The notice period is 30 days.") == "notice period is 30 days"


def test_exact_match_survives_formatting_differences() -> None:
    """Same claim, different typography, must not be scored as a different answer."""
    assert exact_match("The notice period is 30 days.", "notice period is 30 days") == 1.0


def test_exact_match_rejects_a_different_number() -> None:
    """The whole point of the metric: 30 and 60 are not the same answer."""
    assert exact_match("The notice period is 30 days", "The notice period is 60 days") == 0.0


# ---------------------------------------------------------------------------
# token F1
# ---------------------------------------------------------------------------


def test_an_identical_answer_scores_one() -> None:
    assert token_f1("Probation is three months", "Probation is three months") == 1.0


def test_a_disjoint_answer_scores_zero() -> None:
    assert token_f1("Laptops are replaced every three years", "Salaries are paid monthly") == 0.0


def test_f1_refuses_to_reward_padding() -> None:
    """**The way this metric is usually broken.**

    The prediction below contains *every* token of the gold answer and then four more
    sentences of unrelated handbook. Recall is therefore 1.0, and a metric that reported
    recall while calling it F1 would score this a perfect answer -- which is exactly
    backwards, because burying the answer in noise is worse, not better.

    Gold tokens after normalisation and stop-word removal: standard, notice, period, 30,
    days -> 5. The padded prediction keeps 18 after the same treatment (the stop words
    "is", "and", "are" and "on" are dropped). Overlap is all 5 of the gold tokens, so
    precision is 5/18 = 0.278, recall is 5/5 = 1.0, and F1 is
    2 * 0.278 * 1.0 / 1.278 = 0.435.
    """
    gold = "The standard notice period is 30 days"
    padded = (
        "The standard notice period is 30 days and leave accrues monthly and laptops "
        "are replaced every three years and salaries are paid on the last working day"
    )
    score = token_f1(padded, gold)
    assert score < 0.5, f"padding scored {score:.3f}; this metric is reporting recall"
    assert round(score, 3) == 0.435


def test_f1_rewards_a_tight_answer_over_a_padded_one() -> None:
    gold = "The standard notice period is 30 days"
    tight = "The notice period is 30 days"
    padded = gold + " and leave accrues monthly and laptops are replaced every three years"
    assert token_f1(tight, gold) > token_f1(padded, gold)


def test_f1_counts_tokens_as_a_multiset() -> None:
    """Repeating a token must not match it as many times as the reference used it.

    "days days days" against a reference using "days" once has one token in common, not
    three; a set-based intersection would lose that distinction entirely.
    """
    assert token_f1("days days days", "days") < 1.0


def test_two_empty_answers_agree() -> None:
    assert token_f1("", "") == 1.0
    assert token_f1("something", "") == 0.0


# ---------------------------------------------------------------------------
# citation metrics
# ---------------------------------------------------------------------------


def test_a_citation_to_an_unretrieved_passage_is_not_supported() -> None:
    """**The way this metric is usually broken.**

    ``hr-notice#0`` is a real passage in a real document. It was never retrieved for this
    question, so the model cannot have read it, and whatever the answer said about it was
    not grounded in it. Precision must therefore be 1/2.

    Checking the citation against the *corpus* rather than against what was retrieved
    would score this 2/2 -- passing the one case the metric exists to catch.
    """
    score = citation_metrics(
        cited=["hr-leave#0", "hr-notice#0"],
        gold=["hr-leave#0"],
        retrieved=["hr-leave#0", "hr-leave#1"],
    )
    assert score.precision == 0.5
    assert score.supported == 1
    assert score.cited == 2


def test_perfect_citations_score_one() -> None:
    score = citation_metrics(
        cited=["hr-leave#0"], gold=["hr-leave#0"], retrieved=["hr-leave#0", "hr-leave#1"]
    )
    assert score.precision == 1.0
    assert score.recall == 1.0


def test_missing_a_required_citation_costs_recall() -> None:
    """Two passages were needed and one was given: recall 0.5, precision still 1.0."""
    score = citation_metrics(
        cited=["hr-probation#0"],
        gold=["hr-probation#0", "hr-notice#0"],
        retrieved=["hr-probation#0", "hr-notice#0"],
    )
    assert score.recall == 0.5
    assert score.precision == 1.0


def test_citing_nothing_is_vacuously_precise_but_not_recalled() -> None:
    """An answer with no citations has told no lies and supported nothing."""
    score = citation_metrics(cited=[], gold=["hr-leave#0"], retrieved=["hr-leave#0"])
    assert score.precision == 1.0
    assert score.recall == 0.0


# ---------------------------------------------------------------------------
# refusal metrics
# ---------------------------------------------------------------------------


def test_balanced_accuracy_exposes_a_system_that_never_refuses() -> None:
    """**The way this metric is usually broken.**

    The evaluation set holds 27 answerable questions and 7 unanswerable ones, because
    that is the ratio people actually ask in. A system that answers everything gets all
    27 right and all 7 wrong.

    Plain accuracy: 27/34 = 0.794, which reads like a good system.
    Balanced accuracy: (27/27 + 0/7) / 2 = 0.5, which reads like a coin toss.

    The second is the truth about the behaviour being measured, and it is why the
    headline number is the balanced one.
    """
    decisions = [(True, True)] * 27 + [(False, True)] * 7
    score = refusal_metrics(decisions)

    assert round(score.plain_accuracy, 3) == 0.794
    assert score.balanced_accuracy == 0.5
    assert score.answer_recall == 1.0
    assert score.refusal_recall == 0.0


def test_balanced_accuracy_also_exposes_a_system_that_always_refuses() -> None:
    """The mirror image, which plain accuracy scores at 0.206 and balanced at 0.5."""
    decisions = [(True, False)] * 27 + [(False, False)] * 7
    score = refusal_metrics(decisions)
    assert round(score.plain_accuracy, 3) == 0.206
    assert score.balanced_accuracy == 0.5


def test_a_correct_system_scores_one_on_both() -> None:
    decisions = [(True, True)] * 27 + [(False, False)] * 7
    score = refusal_metrics(decisions)
    assert score.balanced_accuracy == 1.0
    assert score.plain_accuracy == 1.0


def test_each_class_is_weighted_equally_regardless_of_size() -> None:
    """One unanswerable question carries as much weight as all twenty-seven others.

    That is the property: adding more answerable questions to the set must not make
    refusal behaviour matter less.
    """
    one_each_wrong = refusal_metrics([(True, True)] * 27 + [(False, True)])
    assert one_each_wrong.balanced_accuracy == 0.5
