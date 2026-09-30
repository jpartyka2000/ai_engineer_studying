"""Pure grading arithmetic: weighted score, gates, and the letter scale.

This module deliberately imports nothing from Django and performs no I/O. That
keeps the cutoff table a single source of truth and makes every score-and-gate
combination exhaustively testable without a database.

The service layer calls into here; **models must not**. Computing derived grade
values in ``Model.save()`` is how ``apps/coding`` ended up with two disagreeing
definitions of its dedup hash (``description[:200]`` in one place,
``description[:500]`` in another).

Design notes:

* The letter scale is the standard US 13-point scale. It is not configurable --
  a letter grade only means something if it means the same thing every time.
* Gates are **caps**, not adjustments. A cap can only lower a grade, never raise
  it, so adding a gate can never inflate a historical result.
* Two gates (tampering, empty submission) are absolute rather than caps, because
  both are unambiguous and mechanically detected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Final

# Ordered best-to-worst. The integer is the minimum weighted score for that
# letter; the table is scanned top-down so the first match wins.
LETTER_CUTOFFS: Final[tuple[tuple[str, int], ...]] = (
    ("A+", 97),
    ("A", 93),
    ("A-", 90),
    ("B+", 87),
    ("B", 83),
    ("B-", 80),
    ("C+", 77),
    ("C", 73),
    ("C-", 70),
    ("D+", 67),
    ("D", 63),
    ("D-", 60),
    ("F", 0),
)

#: All 13 letters, best first. Index doubles as rank (lower is better).
LETTERS_BEST_FIRST: Final[tuple[str, ...]] = tuple(letter for letter, _ in LETTER_CUTOFFS)

#: Conventional 4.0-scale points, with A+ at 4.3 so it is distinguishable from A.
GRADE_POINTS: Final[dict[str, str]] = {
    "A+": "4.30",
    "A": "4.00",
    "A-": "3.70",
    "B+": "3.30",
    "B": "3.00",
    "B-": "2.70",
    "C+": "2.30",
    "C": "2.00",
    "C-": "1.70",
    "D+": "1.30",
    "D": "1.00",
    "D-": "0.70",
    "F": "0.00",
}

# Dimension weights. Correctness dominates because "is the problem actually solved" is
# the final arbiter; documentation is first-class, so a silent fix cannot earn an A.
#
# Documentation was 25% until it was checked against human judgment, and 25% was too
# much. Two hand-graded submissions -- identical working code to their documented twins,
# one with an explanatory comment and one without -- were called B and B- by the user
# where the rubric said C+ and C-. Solving each for the weight that would produce the
# human letter gave 18.2% and 14.7%; 15% is the conservative end of that range, and at
# it the two land B (exact) and C+ (one step, inside tolerance).
#
# The consequences are deliberate. A correct, complete, undocumented fix now reaches
# B-/B rather than C-/C, and an explanatory comment is worth about one letter step --
# which is what the user said it should be worth. Writing the work up is still worth
# roughly three letters, asserted independently of these numbers in
# tests/regression/test_workspace_rubric_conformance.py.
#
# Changing these restates every historical grade, which is why grades record their
# RUBRIC_VERSION. Do not change them again without new hand-graded evidence.
WEIGHT_CORRECTNESS: Final[float] = 0.50
WEIGHT_ENGINEERING: Final[float] = 0.25
WEIGHT_DOCUMENTATION: Final[float] = 0.15
WEIGHT_COMPLETENESS: Final[float] = 0.10

# Gate identifiers, stored on the grade so the UI can explain a cap rather than
# presenting an unexplained letter.
GATE_UNSOLVED: Final[str] = "G1_unsolved"
GATE_NOTHING_SOLVED: Final[str] = "G2_nothing_solved"
GATE_REGRESSION: Final[str] = "G3_regression"
GATE_TAMPERING: Final[str] = "G4_test_tampering"
GATE_EMPTY: Final[str] = "G5_empty_submission"
GATE_NOT_EXCEPTIONAL: Final[str] = "G7_not_exceptional"

GATE_EXPLANATIONS: Final[dict[str, str]] = {
    GATE_UNSOLVED: (
        "At least one required acceptance check is still failing, so the problem "
        "is not solved. Capped at C+."
    ),
    GATE_NOTHING_SOLVED: ("No required acceptance check passes. Capped at D+."),
    GATE_REGRESSION: (
        "The change broke at least one test that was passing before you started. Capped at B."
    ),
    GATE_TAMPERING: (
        "A protected test, fixture or benchmark file was modified. The exercise is graded F."
    ),
    GATE_EMPTY: ("Nothing was submitted: no commits, no changes, and an untouched NOTES.md."),
    GATE_NOT_EXCEPTIONAL: (
        "A+ additionally requires every required check passing, no regressions, at "
        "least one stretch goal, documentation at 95 or above, and submitting with "
        "at least 10% of the time left. Capped at A."
    ),
}

#: A+ requires documentation at least this high, on top of the numeric score.
APLUS_MIN_DOCUMENTATION: Final[int] = 95

#: A+ requires submitting with at least this fraction of the time box unused.
APLUS_MIN_FRACTION_REMAINING: Final[float] = 0.10

#: Exercise type eligible for the speed bonus. Its brief is literally "fix a
#: critical bug *fast*", so speed is part of the task rather than a side metric.
SPEED_BONUS_EXERCISE_TYPE: Final[str] = "critical_bug"
SPEED_BONUS_POINTS: Final[int] = 3
SPEED_BONUS_MAX_FRACTION_USED: Final[float] = 0.50


@dataclass(frozen=True)
class DimensionScores:
    """The four rubric dimensions, each 0-100."""

    correctness: int
    engineering: int
    documentation: int
    completeness: int

    def weighted(self) -> int:
        """Return the weighted 0-100 score, rounded to an integer."""
        total = (
            self.correctness * WEIGHT_CORRECTNESS
            + self.engineering * WEIGHT_ENGINEERING
            + self.documentation * WEIGHT_DOCUMENTATION
            + self.completeness * WEIGHT_COMPLETENESS
        )
        return int(round(total))


@dataclass(frozen=True)
class GateSignals:
    """Mechanically-determined facts about a submission that drive the gates.

    Every field here is objective. Nothing on this dataclass is an LLM judgment,
    which is what makes gate behaviour reproducible.
    """

    required_checks_total: int = 0
    required_checks_passed: int = 0
    regressions: int = 0
    tampering_detected: bool = False
    is_empty_submission: bool = False
    timed_out: bool = False
    stretch_checks_passed: int = 0
    documentation_score: int = 0
    fraction_time_used: float = 1.0
    exercise_type: str = ""

    @property
    def all_required_passed(self) -> bool:
        """Whether every required check passed.

        Vacuously true when an exercise declares no required checks, so an
        all-judgment exercise is not permanently capped.
        """
        if self.required_checks_total == 0:
            return True
        return self.required_checks_passed >= self.required_checks_total

    @property
    def fraction_time_remaining(self) -> float:
        """Fraction of the time box left unused, clamped to 0.0-1.0."""
        return max(0.0, min(1.0, 1.0 - self.fraction_time_used))


@dataclass(frozen=True)
class GradeOutcome:
    """The result of turning a weighted score plus signals into a letter."""

    letter: str
    score: int
    base_score: int
    grade_points: Decimal
    uncapped_letter: str
    applied_caps: tuple[str, ...] = field(default_factory=tuple)
    speed_bonus: int = 0

    @property
    def was_capped(self) -> bool:
        """Whether any gate lowered the grade below its numeric score."""
        return bool(self.applied_caps)

    def cap_explanations(self) -> tuple[str, ...]:
        """Return human-readable reasons for each applied cap, in order."""
        return tuple(GATE_EXPLANATIONS[code] for code in self.applied_caps)


def score_to_letter(score: int) -> str:
    """Map a 0-100 weighted score to a letter grade.

    Args:
        score: The weighted score. Values outside 0-100 are clamped.

    Returns:
        One of the 13 letters, e.g. ``"B+"``.
    """
    clamped = max(0, min(100, int(score)))
    for letter, minimum in LETTER_CUTOFFS:
        if clamped >= minimum:
            return letter
    return "F"  # pragma: no cover - the table's final row has minimum 0


def letter_rank(letter: str) -> int:
    """Return a letter's rank, where 0 is A+ and 12 is F.

    Args:
        letter: A letter from the 13-point scale.

    Returns:
        The index of the letter in :data:`LETTERS_BEST_FIRST`.

    Raises:
        ValueError: If the letter is not on the scale.
    """
    try:
        return LETTERS_BEST_FIRST.index(letter)
    except ValueError:
        raise ValueError(f"{letter!r} is not a valid letter grade") from None


def cap_letter(letter: str, cap: str) -> str:
    """Return the worse of two letters.

    Args:
        letter: The letter earned on the numeric score.
        cap: The maximum letter a gate permits.

    Returns:
        ``cap`` if it is worse than ``letter``, otherwise ``letter``. A cap never
        raises a grade.
    """
    return cap if letter_rank(cap) > letter_rank(letter) else letter


def letter_to_points(letter: str) -> Decimal:
    """Convert a letter to its 4.0-scale grade points.

    Stored alongside the letter so progress over time can be averaged
    numerically instead of by sorting strings.

    Args:
        letter: A letter from the 13-point scale.

    Returns:
        The grade points, e.g. ``Decimal("3.30")`` for ``"B+"``.

    Raises:
        ValueError: If the letter is not on the scale.
    """
    try:
        return Decimal(GRADE_POINTS[letter])
    except KeyError:
        raise ValueError(f"{letter!r} is not a valid letter grade") from None


def speed_bonus_for(signals: GateSignals) -> int:
    """Return the speed bonus earned, in score points.

    Only "fix a critical bug fast" exercises are eligible, and only for a fully
    passing fix delivered in under half the time box. Speed is otherwise not a
    rubric dimension -- the timer is a constraint, not a criterion.

    Args:
        signals: The submission's objective signals.

    Returns:
        :data:`SPEED_BONUS_POINTS` if earned, otherwise 0.
    """
    if signals.exercise_type != SPEED_BONUS_EXERCISE_TYPE:
        return 0
    if not signals.all_required_passed or signals.regressions:
        return 0
    if signals.fraction_time_used >= SPEED_BONUS_MAX_FRACTION_USED:
        return 0
    return SPEED_BONUS_POINTS


def apply_gates(weighted_score: int, signals: GateSignals) -> GradeOutcome:
    """Turn a weighted score into a final letter grade, applying every gate.

    Order matters. The two absolute gates (tampering, empty) short-circuit to F.
    Otherwise the speed bonus is added first, the numeric letter is derived, and
    then each cap is applied in turn -- caps compose, and the worst one wins.

    Note that running out of time is deliberately **not** a gate. The time box
    exists to make the exercise realistic under pressure; failing the buzzer
    automatically would punish exactly the partial-work-plus-honest-writeup
    behaviour the 25% documentation weight is meant to reward. An empty
    submission is already caught by the empty-submission gate.

    Args:
        weighted_score: The 0-100 weighted rubric score.
        signals: Objective facts about the submission.

    Returns:
        The final :class:`GradeOutcome`, including which caps were applied.
    """
    base = max(0, min(100, int(weighted_score)))

    # Absolute gates. Both are mechanically detected and unambiguous, so they do
    # not merely cap the grade.
    if signals.tampering_detected:
        return GradeOutcome(
            letter="F",
            score=0,
            base_score=base,
            grade_points=letter_to_points("F"),
            uncapped_letter=score_to_letter(base),
            applied_caps=(GATE_TAMPERING,),
        )
    if signals.is_empty_submission:
        return GradeOutcome(
            letter="F",
            score=0,
            base_score=base,
            grade_points=letter_to_points("F"),
            uncapped_letter=score_to_letter(base),
            applied_caps=(GATE_EMPTY,),
        )

    bonus = speed_bonus_for(signals)
    score = min(100, base + bonus)
    uncapped = score_to_letter(score)
    letter = uncapped
    caps: list[str] = []

    if signals.required_checks_total:
        if signals.required_checks_passed == 0:
            letter = cap_letter(letter, "D+")
            caps.append(GATE_NOTHING_SOLVED)
        elif not signals.all_required_passed:
            letter = cap_letter(letter, "C+")
            caps.append(GATE_UNSOLVED)

    if signals.regressions:
        letter = cap_letter(letter, "B")
        caps.append(GATE_REGRESSION)

    # A+ has to mean more than a high number, or it reduces to "a well-commented
    # pass". The stretch-goal requirement is what makes it a distinct tier.
    #
    # Tested against `letter`, not `uncapped`: if a stricter cap has already
    # pulled the grade below A+, this gate is moot, and recording it anyway would
    # show the user "capped at A" underneath a B.
    if letter == "A+":
        exceptional = (
            signals.all_required_passed
            and not signals.regressions
            and signals.stretch_checks_passed >= 1
            and signals.documentation_score >= APLUS_MIN_DOCUMENTATION
            and signals.fraction_time_remaining >= APLUS_MIN_FRACTION_REMAINING
        )
        if not exceptional:
            letter = cap_letter(letter, "A")
            caps.append(GATE_NOT_EXCEPTIONAL)

    return GradeOutcome(
        letter=letter,
        score=score,
        base_score=base,
        grade_points=letter_to_points(letter),
        uncapped_letter=uncapped,
        applied_caps=tuple(caps),
        speed_bonus=bonus,
    )


#: The ceiling each gate imposes. Kept beside the gate identifiers so the two cannot
#: drift apart, and used by :func:`regrade_with_recorded_caps`.
GATE_CEILINGS: Final[dict[str, str]] = {
    GATE_TAMPERING: "F",
    GATE_EMPTY: "F",
    GATE_NOTHING_SOLVED: "D+",
    GATE_UNSOLVED: "C+",
    GATE_REGRESSION: "B",
    GATE_NOT_EXCEPTIONAL: "A",
}


def regrade_with_recorded_caps(
    dimensions: DimensionScores, applied_caps: list[str], *, speed_bonus: int = 0
) -> GradeOutcome:
    """Recompute a letter from stored dimension scores and the caps already recorded.

    For re-deriving historical grades after a **weight** change. The dimension scores are
    the model's judgment and do not depend on the weights, so a weight change needs
    arithmetic rather than another API call -- re-running the model would also introduce
    sampling noise and make the before/after uninterpretable.

    Deliberately replays the recorded caps rather than recomputing them from signals:
    which gates fired is a fact about that submission, already decided, and reconstructing
    :class:`GateSignals` from stored rows would be guesswork.

    Args:
        dimensions: The stored dimension scores.
        applied_caps: The gate identifiers recorded on the original grade.
        speed_bonus: Any bonus the original grade recorded.

    Returns:
        A :class:`GradeOutcome` under the current weights.

    Raises:
        ValueError: If a cap identifier is not a known gate, rather than silently
            ignoring it and returning a grade that skipped a cap.
    """
    unknown = [cap for cap in applied_caps if cap not in GATE_CEILINGS]
    if unknown:
        raise ValueError(f"unknown gate identifier(s): {unknown}")

    base = max(0, min(100, dimensions.weighted()))
    if GATE_TAMPERING in applied_caps or GATE_EMPTY in applied_caps:
        absolute = GATE_TAMPERING if GATE_TAMPERING in applied_caps else GATE_EMPTY
        return GradeOutcome(
            letter="F",
            score=0,
            base_score=base,
            grade_points=letter_to_points("F"),
            uncapped_letter=score_to_letter(base),
            applied_caps=(absolute,),
        )

    score = min(100, base + speed_bonus)
    uncapped = score_to_letter(score)
    letter = uncapped
    for cap in applied_caps:
        letter = cap_letter(letter, GATE_CEILINGS[cap])

    return GradeOutcome(
        letter=letter,
        score=score,
        base_score=base,
        grade_points=letter_to_points(letter),
        uncapped_letter=uncapped,
        applied_caps=tuple(applied_caps),
        speed_bonus=speed_bonus,
    )


def grade(dimensions: DimensionScores, signals: GateSignals) -> GradeOutcome:
    """Compute a final grade from dimension scores and objective signals.

    The single entry point callers should use.

    Args:
        dimensions: The four rubric dimension scores, each 0-100.
        signals: Objective facts about the submission.

    Returns:
        The final :class:`GradeOutcome`.
    """
    return apply_gates(dimensions.weighted(), signals)
