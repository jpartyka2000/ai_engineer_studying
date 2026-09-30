"""Assert the rubric produces the outcomes the plan specifies for known submissions.

This is the plan's V5 grading smoke test: four synthetic submissions with asserted
letters, which prove the *grader* works rather than that an exercise is well formed.

    empty submission                     -> F   (gate G5)
    reference patch + good NOTES.md      -> A- or better
    reference patch + empty NOTES.md     -> C+..B-
    tampered (an assertion commented out) -> F  (gate G4)

The two gate cases are decided by arithmetic alone, so they are asserted directly and
run everywhere. The two model-judged cases cannot be, so they are asserted two ways:

* **Reachability** -- that the dimension scores the prompt *instructs* the model to
  produce actually land in the asserted band. This is what caught the real defect: a
  missing writeup was being charged in three dimensions at once, which put the
  undocumented case at F..C and made the specified band unreachable no matter how well
  the model followed the rest of the prompt. Arithmetic, so it always runs.
* **Observed** -- that a built calibration round agrees. Skipped when no round exists,
  since the corpus is round-local and regenerable.

The band in this file is the authored target from the plan, not a measured fact. If it
is ever changed, that is a deliberate decision about what undocumented work is worth,
and it belongs in a commit message.
"""

import json
from pathlib import Path

import pytest

from apps.workspace.calibration import store
from apps.workspace.grading import (
    GATE_EMPTY,
    GATE_TAMPERING,
    DimensionScores,
    GateSignals,
    apply_gates,
    letter_rank,
    score_to_letter,
)

#: "reference patch + good NOTES.md -> A- or better"
GOOD_WRITEUP_FLOOR = "A-"

#: Anchored on hand-graded submissions rather than on an authored guess.
#:
#: The plan originally asked for B-..C+. An earlier pass widened it to C+..C-, reasoning
#: that an unfilled NOTES.md honestly scores about 15 and that a 25% documentation weight
#: therefore capped the case at C. That was fitting the target to the implementation, and
#: it was wrong: asked directly, the user graded two such submissions B- and B. Those
#: letters implied a documentation weight of 14.7% and 18.2%, the weight moved to 15%,
#: and the band is now the range the user actually gave, one step wider at the top than
#: the plan guessed.
#:
#: Changing these means deciding undocumented work is worth something different, and it
#: needs new hand-graded evidence, not a rebuilt corpus that happens to disagree.
UNDOCUMENTED_BEST = "B"
UNDOCUMENTED_WORST = "C+"

#: Silent personas whose *code* deliberately differs in quality from the reference, so
#: the band does not apply to them. ex-003's undocumented submission uses
#: `filter(tenant_id=..., slug=...)` where the reference routes through
#: `for_tenant()`; that exercise's grading notes say to strongly prefer the latter, so a
#: lower correctness and engineering score there is authored intent rather than the
#: documentation leak this band is about.
BAND_EXEMPT = {"ex-003-export-leaks-across-tenants/silent"}


def in_band(letter: str, best: str, worst: str) -> bool:
    """Whether a letter falls within an inclusive best..worst band."""
    return letter_rank(best) <= letter_rank(letter) <= letter_rank(worst)


# ---------------------------------------------------------------------------
# The two gate cases: arithmetic, no model involved
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("score", [0, 50, 90, 100])
def test_an_empty_submission_is_always_f(score):
    outcome = apply_gates(score, GateSignals(is_empty_submission=True))
    assert outcome.letter == "F"
    assert GATE_EMPTY in outcome.applied_caps


@pytest.mark.parametrize("score", [0, 50, 90, 100])
def test_a_tampered_submission_is_always_f(score):
    """Even a perfect numeric score cannot survive editing a protected test."""
    outcome = apply_gates(
        score,
        GateSignals(tampering_detected=True, required_checks_total=5, required_checks_passed=5),
    )
    assert outcome.letter == "F"
    assert GATE_TAMPERING in outcome.applied_caps


# ---------------------------------------------------------------------------
# Reachability: do the prompt's own instructions land in the asserted bands?
# ---------------------------------------------------------------------------


def solved() -> GateSignals:
    """Signals for a fully passing submission with no regressions."""
    return GateSignals(
        required_checks_total=5,
        required_checks_passed=5,
        stretch_checks_passed=1,
        documentation_score=97,
        fraction_time_used=0.65,
    )


def test_a_staff_quality_documented_fix_reaches_the_good_writeup_floor():
    """The prompt's "95 and above is what a staff engineer would ship" anchor."""
    letter = apply_gates(
        DimensionScores(
            correctness=96, engineering=95, documentation=96, completeness=97
        ).weighted(),
        solved(),
    ).letter
    assert letter_rank(letter) <= letter_rank(GOOD_WRITEUP_FLOOR), letter


@pytest.mark.parametrize(
    ("correctness", "engineering", "completeness"),
    [
        # The V5 case is the *reference patch* with the writeup removed, so its code
        # dimensions score like the reference. Measured on the documented versions of
        # the same submissions: engineering 94-96, completeness 96-98.
        (92, 94, 98),
        (95, 90, 95),
        (96, 95, 97),
    ],
)
def test_undocumented_reference_quality_work_reaches_the_specified_band(
    correctness, engineering, completeness
):
    """Documentation at its stated ~30, with nothing else charged for the writeup.

    Failing this means the band cannot be hit however faithfully the model follows the
    prompt -- which is exactly the state the rubric was in when a missing writeup was
    deducted in three dimensions at once.
    """
    signals = GateSignals(required_checks_total=5, required_checks_passed=5, documentation_score=30)
    score = DimensionScores(
        correctness=correctness,
        engineering=engineering,
        documentation=30,
        completeness=completeness,
    ).weighted()
    letter = apply_gates(score, signals).letter
    assert in_band(letter, UNDOCUMENTED_BEST, UNDOCUMENTED_WORST), (
        f"correctness={correctness} engineering={engineering} documentation=30 "
        f"completeness={completeness} -> {score} ({letter}), outside "
        f"{UNDOCUMENTED_BEST}..{UNDOCUMENTED_WORST}"
    )


#: How many letter steps the writeup must be worth. This is the "documentation has
#: teeth" property the band exists to express, and unlike the band itself it does not
#: depend on where the cutoffs happen to fall.
#:
#: Three, measured at documentation's recalibrated 15% weight. It was six at 25%, which
#: the user judged too expensive. Three is also what their own letters imply: they graded
#: undocumented submissions B- and B against documented twins the rubric puts at A/A+.
MIN_WRITEUP_GAP_STEPS = 3


def test_the_writeup_is_worth_several_letters_on_otherwise_identical_work():
    """Same code, same tests, same commits -- only the writeup differs.

    Asserted as a *gap* rather than an absolute band because the gap is the thing that
    matters and the thing that survives a cutoff change. Widening the band must never be
    a way to quietly make documentation cheap.
    """
    code = {"correctness": 96, "engineering": 95, "completeness": 97}
    documented = DimensionScores(documentation=96, **code).weighted()
    undocumented = DimensionScores(documentation=15, **code).weighted()

    gap = letter_rank(score_to_letter(undocumented)) - letter_rank(score_to_letter(documented))
    assert gap >= MIN_WRITEUP_GAP_STEPS, (
        f"documented {documented} ({score_to_letter(documented)}) vs undocumented "
        f"{undocumented} ({score_to_letter(undocumented)}) is only {gap} steps"
    )


def test_charging_the_missing_writeup_three_times_breaks_the_band():
    """Pins the defect itself, so a prompt edit cannot quietly reintroduce it.

    These are the dimension scores actually observed before the fix: documentation at
    half its stated anchor, and completeness and engineering dragged down by the same
    omission. The band is unreachable from here, which is the point.
    """
    triple_charged = DimensionScores(
        correctness=92, engineering=85, documentation=15, completeness=55
    ).weighted()
    assert not in_band(score_to_letter(triple_charged), UNDOCUMENTED_BEST, UNDOCUMENTED_WORST), (
        "the pre-fix dimension scores should NOT satisfy the band"
    )

    # The only differences below are the three leaks being closed.
    repaired = DimensionScores(
        correctness=92, engineering=94, documentation=30, completeness=98
    ).weighted()
    assert in_band(score_to_letter(repaired), UNDOCUMENTED_BEST, UNDOCUMENTED_WORST)


# ---------------------------------------------------------------------------
# Observed: does a built calibration round agree?
# ---------------------------------------------------------------------------


def recorded_round() -> list[dict]:
    """Return the current calibration round, or skip when none has been built."""
    path = Path(store.answer_key_path())
    if not path.is_file():
        pytest.skip("no calibration round built; run `calibrate_workspace build`")
    items = [
        e
        for e in json.loads(path.read_text(encoding="utf-8")).get("items", [])
        if e.get("system_letter")
    ]
    if not items:
        pytest.skip("calibration round has no graded items")
    return items


def test_recorded_documented_reference_fixes_meet_the_floor():
    offenders = [
        (e["persona_key"], e["system_letter"])
        for e in recorded_round()
        if e["persona_id"] == "root-cause"
        and letter_rank(e["system_letter"]) > letter_rank(GOOD_WRITEUP_FLOOR)
    ]
    assert not offenders, f"below {GOOD_WRITEUP_FLOOR}: {offenders}"


def test_recorded_undocumented_reference_fixes_land_in_the_band():
    """The case the rubric was getting wrong, asserted against real grades."""
    offenders = [
        (e["persona_key"], e["system_letter"], e["system_score"])
        for e in recorded_round()
        if e["persona_id"] == "silent"
        and e["persona_key"] not in BAND_EXEMPT
        and not in_band(e["system_letter"], UNDOCUMENTED_BEST, UNDOCUMENTED_WORST)
    ]
    assert not offenders, f"outside {UNDOCUMENTED_BEST}..{UNDOCUMENTED_WORST}: {offenders}"
