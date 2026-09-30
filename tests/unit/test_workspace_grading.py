"""Tests for the pure grading arithmetic: weights, letters, and gates.

The module under test has no Django dependency and no I/O, so every score-and-gate
combination can be covered exhaustively and cheaply.
"""

from decimal import Decimal

import pytest

from apps.workspace import grading
from apps.workspace.grading import DimensionScores, GateSignals


def solved(**overrides) -> GateSignals:
    """Signals for a clean, fully-solved, no-regression submission."""
    defaults = {
        "required_checks_total": 5,
        "required_checks_passed": 5,
        "regressions": 0,
        "tampering_detected": False,
        "is_empty_submission": False,
        "stretch_checks_passed": 1,
        "documentation_score": 100,
        "fraction_time_used": 0.7,
        "exercise_type": "tenant_isolation",
    }
    return GateSignals(**{**defaults, **overrides})


# ---------------------------------------------------------------------------
# The letter scale
# ---------------------------------------------------------------------------


def test_all_thirteen_letters_are_present_and_ordered():
    assert grading.LETTERS_BEST_FIRST == (
        "A+",
        "A",
        "A-",
        "B+",
        "B",
        "B-",
        "C+",
        "C",
        "C-",
        "D+",
        "D",
        "D-",
        "F",
    )


def test_cutoffs_are_strictly_descending():
    minimums = [minimum for _, minimum in grading.LETTER_CUTOFFS]
    assert minimums == sorted(minimums, reverse=True)
    assert len(set(minimums)) == len(minimums)


def test_every_letter_has_grade_points():
    assert set(grading.GRADE_POINTS) == set(grading.LETTERS_BEST_FIRST)


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (100, "A+"),
        (97, "A+"),
        (96, "A"),
        (93, "A"),
        (92, "A-"),
        (90, "A-"),
        (89, "B+"),
        (87, "B+"),
        (86, "B"),
        (83, "B"),
        (82, "B-"),
        (80, "B-"),
        (79, "C+"),
        (77, "C+"),
        (76, "C"),
        (73, "C"),
        (72, "C-"),
        (70, "C-"),
        (69, "D+"),
        (67, "D+"),
        (66, "D"),
        (63, "D"),
        (62, "D-"),
        (60, "D-"),
        (59, "F"),
        (0, "F"),
    ],
)
def test_score_to_letter_boundaries(score, expected):
    assert grading.score_to_letter(score) == expected


@pytest.mark.parametrize("score", range(0, 101))
def test_score_to_letter_covers_every_score(score):
    """Exhaustive: every score in 0-100 maps to a real letter."""
    assert grading.score_to_letter(score) in grading.LETTERS_BEST_FIRST


@pytest.mark.parametrize("score", range(0, 101))
def test_score_to_letter_is_monotonic(score):
    """A higher score can never produce a worse letter."""
    if score == 0:
        return
    this = grading.letter_rank(grading.score_to_letter(score))
    lower = grading.letter_rank(grading.score_to_letter(score - 1))
    assert this <= lower


def test_score_to_letter_clamps_out_of_range():
    assert grading.score_to_letter(150) == "A+"
    assert grading.score_to_letter(-20) == "F"


def test_letter_rank_rejects_an_unknown_letter():
    with pytest.raises(ValueError, match="not a valid letter"):
        grading.letter_rank("E")


def test_letter_to_points():
    assert grading.letter_to_points("A+") == Decimal("4.30")
    assert grading.letter_to_points("B") == Decimal("3.00")
    assert grading.letter_to_points("F") == Decimal("0.00")


def test_letter_to_points_rejects_an_unknown_letter():
    with pytest.raises(ValueError, match="not a valid letter"):
        grading.letter_to_points("E")


# ---------------------------------------------------------------------------
# cap_letter
# ---------------------------------------------------------------------------


def test_cap_lowers_a_better_grade():
    assert grading.cap_letter("A+", "C+") == "C+"


def test_cap_never_raises_a_worse_grade():
    """The core invariant: a cap can only lower."""
    assert grading.cap_letter("D-", "B") == "D-"


def test_cap_is_a_noop_when_equal():
    assert grading.cap_letter("B", "B") == "B"


@pytest.mark.parametrize("letter", grading.LETTERS_BEST_FIRST)
@pytest.mark.parametrize("cap", grading.LETTERS_BEST_FIRST)
def test_cap_is_never_better_than_either_input(letter, cap):
    """Exhaustive over all 169 letter/cap pairs."""
    result = grading.cap_letter(letter, cap)
    assert grading.letter_rank(result) >= grading.letter_rank(letter)
    assert result in (letter, cap)


# ---------------------------------------------------------------------------
# Weighting
# ---------------------------------------------------------------------------


def test_weights_sum_to_one():
    total = (
        grading.WEIGHT_CORRECTNESS
        + grading.WEIGHT_ENGINEERING
        + grading.WEIGHT_DOCUMENTATION
        + grading.WEIGHT_COMPLETENESS
    )
    assert total == pytest.approx(1.0)


def test_weighted_score_of_all_hundreds_is_one_hundred():
    assert DimensionScores(100, 100, 100, 100).weighted() == 100


def test_weighted_score_of_all_zeros_is_zero():
    assert DimensionScores(0, 0, 0, 0).weighted() == 0


def test_correctness_dominates_the_weighting():
    """Correctness must outweigh any single other dimension."""
    only_correct = DimensionScores(100, 0, 0, 0).weighted()
    for other in (
        DimensionScores(0, 100, 0, 0).weighted(),
        DimensionScores(0, 0, 100, 0).weighted(),
        DimensionScores(0, 0, 0, 100).weighted(),
    ):
        assert only_correct > other


def test_a_perfect_but_undocumented_fix_cannot_reach_an_a():
    """The headline consequence of documentation being weighted at all.

    The exact figure moved when documentation was recalibrated from 25% to 15% against
    hand-graded submissions; what must not move is that a silent fix cannot earn an A,
    however good the code.
    """
    outcome = grading.grade(DimensionScores(100, 100, 0, 100), solved())
    assert outcome.score == 85
    assert outcome.letter == "B"
    assert grading.letter_rank(outcome.letter) > grading.letter_rank("A-")


def test_beautifully_documented_but_unsolved_cannot_beat_a_c_plus():
    """The mirror case: prose cannot substitute for a working fix.

    Perfect engineering, documentation and scope with only partial correctness weights
    to a B-, which the unsolved gate then pulls down to C+. It was a B before
    documentation was recalibrated from 25% to 15%; prose buys one step less than it
    used to, which is the intended mirror of an undocumented fix now scoring higher.
    """
    outcome = grading.grade(
        DimensionScores(60, 100, 100, 100),
        solved(required_checks_passed=2, documentation_score=100),
    )
    assert outcome.uncapped_letter == "B-"
    assert outcome.letter == "C+"
    assert grading.GATE_UNSOLVED in outcome.applied_caps


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


def test_g1_unsolved_caps_at_c_plus():
    outcome = grading.apply_gates(95, solved(required_checks_passed=4))
    assert outcome.letter == "C+"
    assert outcome.uncapped_letter == "A"
    assert outcome.applied_caps == (grading.GATE_UNSOLVED,)
    assert outcome.was_capped


def test_g2_nothing_solved_caps_at_d_plus():
    outcome = grading.apply_gates(95, solved(required_checks_passed=0))
    assert outcome.letter == "D+"
    assert outcome.applied_caps == (grading.GATE_NOTHING_SOLVED,)


def test_g2_takes_precedence_over_g1():
    """Zero passing is worse than some passing; only the stricter cap applies."""
    outcome = grading.apply_gates(95, solved(required_checks_passed=0))
    assert grading.GATE_UNSOLVED not in outcome.applied_caps


def test_g3_regression_caps_at_b():
    outcome = grading.apply_gates(98, solved(regressions=1))
    assert outcome.letter == "B"
    assert grading.GATE_REGRESSION in outcome.applied_caps


def test_g3_still_permits_a_b_not_an_a():
    """Breaking a passing test is serious but not fatal."""
    outcome = grading.apply_gates(99, solved(regressions=3))
    assert grading.letter_rank(outcome.letter) >= grading.letter_rank("B")


def test_g1_and_g3_compose_to_the_worse_cap():
    outcome = grading.apply_gates(99, solved(required_checks_passed=3, regressions=2))
    assert outcome.letter == "C+"
    assert set(outcome.applied_caps) == {grading.GATE_UNSOLVED, grading.GATE_REGRESSION}


def test_g4_tampering_is_a_hard_f_regardless_of_score():
    outcome = grading.apply_gates(100, solved(tampering_detected=True))
    assert outcome.letter == "F"
    assert outcome.score == 0
    assert outcome.applied_caps == (grading.GATE_TAMPERING,)


def test_g4_tampering_beats_every_other_signal():
    outcome = grading.apply_gates(100, solved(tampering_detected=True, stretch_checks_passed=3))
    assert outcome.letter == "F"


def test_g5_empty_submission_is_an_f():
    outcome = grading.apply_gates(0, solved(is_empty_submission=True))
    assert outcome.letter == "F"
    assert outcome.applied_caps == (grading.GATE_EMPTY,)


def test_g6_timing_out_is_not_an_automatic_f():
    """Explicit design decision: the buzzer grades partial work, it does not void it."""
    outcome = grading.apply_gates(85, solved(timed_out=True))
    assert outcome.letter == "B"
    assert outcome.applied_caps == ()


def test_g6_a_timed_out_partial_fix_still_earns_partial_credit():
    """Dimensions measured on a real honest-partial submission, not invented ones.

    The calibration corpus has exactly this case: the Wilson-interval exercise with the
    floating-point boundary unfixed, diagnosed honestly in NOTES.md and flagged
    do-not-ship. It scored correctness 40 (a required check fails), engineering 85,
    documentation 88, completeness 70.
    """
    outcome = grading.grade(
        DimensionScores(40, 85, 88, 70),
        solved(timed_out=True, required_checks_passed=2),
    )
    assert outcome.letter != "F"
    assert grading.GATE_UNSOLVED in outcome.applied_caps


def test_a_partial_fix_carried_mainly_by_its_writeup_can_now_reach_f():
    """A deliberate consequence of documentation dropping from 25% to 15%.

    Weaker code than the case above -- engineering 70, completeness 50 -- with the same
    strong writeup used to weight to D-. It now reaches F, because the writeup is worth
    ten points less and there is not enough else holding it up. Pinned so the trade-off
    stays visible: recalibrating documentation down to stop undocumented work being
    punished necessarily stops prose rescuing work that is mostly unsolved.
    """
    outcome = grading.grade(
        DimensionScores(40, 70, 90, 50),
        solved(timed_out=True, required_checks_passed=2),
    )
    assert outcome.score == 56
    assert outcome.letter == "F"


# ---------------------------------------------------------------------------
# G7: A+ requires more than a number
# ---------------------------------------------------------------------------


def test_a_plus_is_awarded_when_every_condition_is_met():
    outcome = grading.apply_gates(98, solved())
    assert outcome.letter == "A+"
    assert outcome.applied_caps == ()


@pytest.mark.parametrize(
    ("overrides", "why"),
    [
        ({"stretch_checks_passed": 0}, "no stretch goal"),
        ({"documentation_score": 94}, "documentation below 95"),
        ({"fraction_time_used": 0.95}, "less than 10% of the time left"),
    ],
)
def test_a_plus_is_capped_to_a_when_a_condition_is_missing(overrides, why):
    outcome = grading.apply_gates(98, solved(**overrides))
    assert outcome.letter == "A", why
    assert grading.GATE_NOT_EXCEPTIONAL in outcome.applied_caps


def test_g7_does_not_apply_below_an_a_plus_score():
    """A 94 with no stretch goal is simply an A; G7 should not fire."""
    outcome = grading.apply_gates(94, solved(stretch_checks_passed=0))
    assert outcome.letter == "A"
    assert outcome.applied_caps == ()


def test_a_plus_requires_no_regressions():
    outcome = grading.apply_gates(98, solved(regressions=1))
    assert outcome.letter == "B"


# ---------------------------------------------------------------------------
# Speed bonus
# ---------------------------------------------------------------------------


def test_speed_bonus_applies_to_a_fast_critical_bug_fix():
    signals = solved(exercise_type="critical_bug", fraction_time_used=0.4)
    outcome = grading.apply_gates(91, signals)
    assert outcome.speed_bonus == 3
    assert outcome.base_score == 91
    assert outcome.score == 94
    assert outcome.letter == "A"


def test_speed_bonus_does_not_apply_to_other_exercise_types():
    signals = solved(exercise_type="tenant_isolation", fraction_time_used=0.4)
    assert grading.speed_bonus_for(signals) == 0


def test_speed_bonus_requires_a_fully_passing_fix():
    signals = solved(exercise_type="critical_bug", fraction_time_used=0.2, required_checks_passed=4)
    assert grading.speed_bonus_for(signals) == 0


def test_speed_bonus_requires_no_regressions():
    signals = solved(exercise_type="critical_bug", fraction_time_used=0.2, regressions=1)
    assert grading.speed_bonus_for(signals) == 0


def test_speed_bonus_requires_under_half_the_time_box():
    signals = solved(exercise_type="critical_bug", fraction_time_used=0.5)
    assert grading.speed_bonus_for(signals) == 0


def test_speed_bonus_cannot_push_the_score_past_one_hundred():
    signals = solved(exercise_type="critical_bug", fraction_time_used=0.1)
    outcome = grading.apply_gates(100, signals)
    assert outcome.score == 100


# ---------------------------------------------------------------------------
# Invariants across the whole space
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("score", range(0, 101, 1))
@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"required_checks_passed": 0},
        {"required_checks_passed": 3},
        {"regressions": 1},
        {"required_checks_passed": 3, "regressions": 1},
        {"stretch_checks_passed": 0},
        {"documentation_score": 10},
        {"fraction_time_used": 1.0},
        {"timed_out": True},
        {"required_checks_total": 0, "required_checks_passed": 0},
    ],
)
def test_a_gate_never_improves_a_grade(score, overrides):
    """Exhaustive: 101 scores x 10 signal shapes, all caps must only lower."""
    outcome = grading.apply_gates(score, solved(**overrides))
    assert grading.letter_rank(outcome.letter) >= grading.letter_rank(outcome.uncapped_letter)


@pytest.mark.parametrize("score", range(0, 101, 7))
def test_grade_points_always_match_the_letter(score):
    outcome = grading.apply_gates(score, solved(required_checks_passed=2))
    assert outcome.grade_points == grading.letter_to_points(outcome.letter)


def test_no_required_checks_does_not_permanently_cap_an_exercise():
    """An all-judgment exercise must still be able to earn an A+."""
    signals = solved(required_checks_total=0, required_checks_passed=0)
    assert signals.all_required_passed
    assert grading.apply_gates(98, signals).letter == "A+"


def test_every_gate_code_has_an_explanation():
    codes = {
        grading.GATE_UNSOLVED,
        grading.GATE_NOTHING_SOLVED,
        grading.GATE_REGRESSION,
        grading.GATE_TAMPERING,
        grading.GATE_EMPTY,
        grading.GATE_NOT_EXCEPTIONAL,
    }
    assert codes == set(grading.GATE_EXPLANATIONS)


def test_cap_explanations_are_returned_in_order():
    outcome = grading.apply_gates(99, solved(required_checks_passed=3, regressions=1))
    explanations = outcome.cap_explanations()
    assert len(explanations) == 2
    assert "not solved" in explanations[0]


def test_fraction_time_remaining_is_clamped():
    assert solved(fraction_time_used=1.4).fraction_time_remaining == 0.0
    assert solved(fraction_time_used=-0.2).fraction_time_remaining == 1.0


# ---------------------------------------------------------------------------
# Re-deriving a historical grade after a weight change
# ---------------------------------------------------------------------------


def test_regrade_replays_a_recorded_cap():
    """The caps are facts about that submission, replayed rather than recomputed."""
    outcome = grading.regrade_with_recorded_caps(
        DimensionScores(95, 95, 95, 95), [grading.GATE_UNSOLVED]
    )
    assert outcome.uncapped_letter == "A"
    assert outcome.letter == "C+"
    assert outcome.applied_caps == (grading.GATE_UNSOLVED,)


def test_regrade_composes_multiple_caps_worst_first():
    outcome = grading.regrade_with_recorded_caps(
        DimensionScores(95, 95, 95, 95), [grading.GATE_REGRESSION, grading.GATE_UNSOLVED]
    )
    assert outcome.letter == "C+"


@pytest.mark.parametrize("gate", [grading.GATE_TAMPERING, grading.GATE_EMPTY])
def test_regrade_keeps_the_absolute_gates_absolute(gate):
    """A weight change must never resurrect a tampered or empty submission."""
    outcome = grading.regrade_with_recorded_caps(DimensionScores(100, 100, 100, 100), [gate])
    assert outcome.letter == "F"
    assert outcome.score == 0


def test_regrade_with_no_caps_is_just_the_weighted_letter():
    outcome = grading.regrade_with_recorded_caps(DimensionScores(96, 95, 96, 97), [])
    assert outcome.letter == outcome.uncapped_letter
    assert outcome.applied_caps == ()


def test_regrade_carries_a_recorded_speed_bonus():
    plain = grading.regrade_with_recorded_caps(DimensionScores(90, 90, 90, 90), [])
    bonused = grading.regrade_with_recorded_caps(DimensionScores(90, 90, 90, 90), [], speed_bonus=3)
    assert bonused.score == plain.score + 3
    assert bonused.speed_bonus == 3


def test_regrade_rejects_an_unknown_cap():
    """Silently ignoring it would return a grade that skipped a gate."""
    with pytest.raises(ValueError, match="unknown gate"):
        grading.regrade_with_recorded_caps(DimensionScores(90, 90, 90, 90), ["G9_invented"])


def test_every_gate_identifier_has_a_ceiling():
    """A new gate must be given a ceiling, or regrading would reject grades using it."""
    gates = {
        value
        for name, value in vars(grading).items()
        if name.startswith("GATE_") and isinstance(value, str)
    }
    assert gates == set(grading.GATE_CEILINGS)
