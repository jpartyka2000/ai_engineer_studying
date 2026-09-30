"""Compare hand-assigned grades against the system's, and say what to change.

Two different questions get answered here, and conflating them is how a rubric gets
"fixed" in the wrong direction:

**Agreement** -- did the system land within one letter of the human on each item? This
is the plan's Phase 1 gate. A systematic offset in one direction (every item one step
harsh) is a calibration-anchor problem, not a weights problem.

**Discrimination** -- did the system *order* the items the way the human did? A rubric
can agree on every letter and still be useless if it cannot tell the strong submission
from the cover-up, and it can disagree on every letter while ordering them perfectly,
which is a far easier fix. Inverted pairs are reported individually because each one
names two submissions whose relative quality the rubric got backwards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from apps.workspace.calibration import store
from apps.workspace.calibration.store import AnswerKeyEntry, HumanGrade
from apps.workspace.grading import (
    WEIGHT_COMPLETENESS,
    WEIGHT_CORRECTNESS,
    WEIGHT_DOCUMENTATION,
    WEIGHT_ENGINEERING,
    letter_rank,
)

#: The plan's Phase 1 gate: agreement to within this many letter steps, on every item.
GATE_MAX_STEPS = 1

#: How far apart the human must place two submissions before the system giving them the
#: same letter counts as a failure to discriminate. Two steps, so a genuine near-tie the
#: human split B+/B is not reported as a problem.
COLLAPSE_MIN_HUMAN_STEPS = 2

DIMENSION_WEIGHTS = {
    "correctness": WEIGHT_CORRECTNESS,
    "engineering": WEIGHT_ENGINEERING,
    "documentation": WEIGHT_DOCUMENTATION,
    "completeness": WEIGHT_COMPLETENESS,
}


@dataclass
class Comparison:
    """One item's human grade set against the system's."""

    entry: AnswerKeyEntry
    human: HumanGrade

    @property
    def steps(self) -> int:
        """Letter steps between the two, positive when the system was harsher."""
        return letter_rank(self.entry.system_letter) - letter_rank(self.human.letter)

    @property
    def agrees(self) -> bool:
        """Whether the two are within the gate's tolerance."""
        return abs(self.steps) <= GATE_MAX_STEPS

    @property
    def direction(self) -> str:
        """Which way the system erred, in words."""
        if self.steps == 0:
            return "exact"
        return "system harsher" if self.steps > 0 else "system lenient"

    def dimension_deltas(self) -> dict[str, int]:
        """Return system-minus-human per dimension, for dimensions the human scored."""
        return {
            key: self.entry.system_dimensions.get(key, 0) - value
            for key, value in self.human.dimensions.items()
        }

    def weighted_contribution(self) -> list[tuple[str, float]]:
        """Return each dimension's contribution to the score gap, largest first.

        A 40-point documentation disagreement moves the weighted score by 10, while the
        same gap on correctness moves it by 16. Ranking by contribution rather than by
        raw delta points at the dimension actually responsible for the letter.
        """
        contributions = [
            (key, delta * DIMENSION_WEIGHTS[key]) for key, delta in self.dimension_deltas().items()
        ]
        return sorted(contributions, key=lambda pair: abs(pair[1]), reverse=True)


@dataclass
class Round:
    """Every comparison in one calibration round."""

    comparisons: list[Comparison] = field(default_factory=list)
    ungraded: list[AnswerKeyEntry] = field(default_factory=list)
    unfilled: list[AnswerKeyEntry] = field(default_factory=list)

    @property
    def scored(self) -> int:
        """How many items could be compared."""
        return len(self.comparisons)

    @property
    def agreed(self) -> int:
        """How many comparisons fell inside the gate."""
        return sum(1 for c in self.comparisons if c.agrees)

    @property
    def gate_passed(self) -> bool:
        """Whether every compared item agreed within tolerance."""
        return bool(self.comparisons) and self.agreed == self.scored

    @property
    def mean_signed_steps(self) -> float:
        """Average signed step delta; a non-zero value is a systematic bias."""
        if not self.comparisons:
            return 0.0
        return sum(c.steps for c in self.comparisons) / len(self.comparisons)

    @property
    def mean_absolute_steps(self) -> float:
        """Average magnitude of disagreement, regardless of direction."""
        if not self.comparisons:
            return 0.0
        return sum(abs(c.steps) for c in self.comparisons) / len(self.comparisons)

    def _within_exercise_pairs(self):
        """Yield ``(left, right, human_gap, system_gap)`` for each same-exercise pair.

        Ordering two submissions to different briefs against each other would not mean
        anything, so pairing never crosses an exercise.
        """
        by_exercise: dict[str, list[Comparison]] = {}
        for comparison in self.comparisons:
            by_exercise.setdefault(comparison.entry.exercise_slug, []).append(comparison)

        for group in by_exercise.values():
            for index, left in enumerate(group):
                for right in group[index + 1 :]:
                    human_gap = letter_rank(right.human.letter) - letter_rank(left.human.letter)
                    system_gap = letter_rank(right.entry.system_letter) - letter_rank(
                        left.entry.system_letter
                    )
                    yield left, right, human_gap, system_gap

    def inversions(self) -> list[tuple[Comparison, Comparison]]:
        """Return pairs the system ranked in the opposite order to the human."""
        return [
            (left, right)
            for left, right, human_gap, system_gap in self._within_exercise_pairs()
            if human_gap and system_gap and (human_gap > 0) != (system_gap > 0)
        ]

    def collapsed_pairs(self) -> list[tuple[Comparison, Comparison]]:
        """Return pairs the human separated but the system gave the same letter.

        A tie is not an inversion -- the rubric did not get the order backwards, it
        failed to have an opinion -- but it is the same kind of failure and must not be
        allowed to pass as agreement. Two submissions of visibly different quality
        landing on one letter is how a rubric ends up sorting work into "fine" and "not
        fine" while claiming a thirteen-point scale.
        """
        return [
            (left, right)
            for left, right, human_gap, system_gap in self._within_exercise_pairs()
            if system_gap == 0 and abs(human_gap) >= COLLAPSE_MIN_HUMAN_STEPS
        ]


def build_round() -> Round:
    """Load the answer key and scoresheet and pair them up.

    Returns:
        A :class:`Round`. Items the system could not grade and items the human has not
        filled in are reported separately rather than silently dropped -- an empty
        comparison set that looks like agreement would be the worst possible output.
    """
    entries = store.read_answer_key()
    sheet_path = store.scoresheet_path()
    grades = (
        store.parse_scoresheet(sheet_path.read_text(encoding="utf-8"))
        if sheet_path.is_file()
        else {}
    )

    round_ = Round()
    for entry in entries:
        if not entry.graded:
            round_.ungraded.append(entry)
            continue
        human = grades.get(entry.item)
        if human is None or not human.filled:
            round_.unfilled.append(entry)
            continue
        round_.comparisons.append(Comparison(entry=entry, human=human))
    return round_


def _dimension_line(comparison: Comparison) -> str:
    """Render the dimension breakdown for one comparison, or a placeholder."""
    contributions = comparison.weighted_contribution()
    if not contributions:
        return "      dimensions: not scored by hand"
    parts = []
    for key, weighted in contributions:
        delta = comparison.dimension_deltas()[key]
        system = comparison.entry.system_dimensions.get(key, 0)
        human = comparison.human.dimensions[key]
        parts.append(f"{key} {human}->{system} ({delta:+d}, {weighted:+.1f} weighted)")
    return "      " + "; ".join(parts)


def render(round_: Round) -> str:
    """Render the comparison report as plain text.

    Args:
        round_: The round to report on.

    Returns:
        The report, ready to print.
    """
    lines: list[str] = ["", "=" * 78, "RUBRIC CALIBRATION -- HUMAN VERSUS SYSTEM", "=" * 78, ""]

    if not round_.comparisons:
        lines += ["Nothing to compare yet.", ""]
        if round_.ungraded:
            lines.append(f"{len(round_.ungraded)} item(s) were never graded by the system:")
            lines += [
                f"  {e.item}  {e.persona_key}  {e.error or 'no grade recorded'}"
                for e in round_.ungraded
            ]
            lines.append("")
        if round_.unfilled:
            lines.append(
                f"{len(round_.unfilled)} item(s) have no hand-assigned letter yet. "
                f"Fill in {store.scoresheet_path()}."
            )
            lines.append("")
        return "\n".join(lines)

    lines += [
        f"{'item':<11} {'exercise':<34} {'you':>4} {'system':>7} {'pred':>5}  delta",
        "-" * 78,
    ]
    for comparison in sorted(round_.comparisons, key=lambda c: letter_rank(c.human.letter)):
        entry = comparison.entry
        flag = "" if comparison.agrees else "  <-- OUTSIDE TOLERANCE"
        lines.append(
            f"{entry.item:<11} {entry.exercise_slug[:34]:<34} "
            f"{comparison.human.letter:>4} {entry.system_letter:>7} "
            f"{entry.predicted_letter:>5}  {comparison.steps:+d} {comparison.direction}{flag}"
        )
        lines.append(f"      persona: {entry.persona_id} -- {entry.tier}")
        lines.append(_dimension_line(comparison))
        details = []
        if entry.applied_caps:
            details.append(f"caps {', '.join(entry.applied_caps)}")
        if entry.symptom_patch_suspected:
            details.append("symptom patch suspected")
        if entry.required_passed:
            details.append(f"required checks {entry.required_passed}")
        if entry.degraded:
            details.append("MODEL REVIEW UNAVAILABLE -- grade was imputed")
        if details:
            lines.append("      " + "; ".join(details))
        if comparison.human.comment:
            lines.append(f"      you: {comparison.human.comment}")
        lines.append("")

    lines += [
        "-" * 78,
        f"Agreement:      {round_.agreed}/{round_.scored} within {GATE_MAX_STEPS} letter step",
        f"Mean |delta|:   {round_.mean_absolute_steps:.2f} letter steps",
        f"Mean delta:     {round_.mean_signed_steps:+.2f} "
        f"({'system runs harsh' if round_.mean_signed_steps > 0.4 else 'system runs lenient' if round_.mean_signed_steps < -0.4 else 'no systematic bias'})",
        "",
    ]

    inversions = round_.inversions()
    if inversions:
        lines.append("ORDERING FAILURES -- the rubric ranked these backwards:")
        for left, right in inversions:
            lines.append(
                f"  you ranked {left.entry.item} ({left.human.letter}) vs "
                f"{right.entry.item} ({right.human.letter}); the system said "
                f"{left.entry.system_letter} vs {right.entry.system_letter}"
            )
            lines.append(
                f"    {left.entry.persona_id} ({left.entry.tier}) "
                f"against {right.entry.persona_id} ({right.entry.tier})"
            )
        lines.append("")
        lines.append(
            "  An inversion is more serious than a letter offset: the rubric cannot "
            "tell these two apart in the right direction, so no amount of shifting "
            "the anchors fixes it. Look at the dimension the pair differs on."
        )
        lines.append("")

    collapsed = round_.collapsed_pairs()
    if collapsed:
        lines.append("COLLAPSED PAIRS -- you separated these, the rubric did not:")
        for left, right in collapsed:
            lines.append(
                f"  {left.entry.item} and {right.entry.item} both scored "
                f"{left.entry.system_letter}; you said {left.human.letter} and "
                f"{right.human.letter}"
            )
            lines.append(
                f"    {left.entry.persona_id} ({left.entry.tier}) "
                f"against {right.entry.persona_id} ({right.entry.tier})"
            )
        lines.append("")
        lines.append(
            "  A tie is not a backwards ranking -- it is the rubric having no opinion "
            "where you had a clear one. Read the two submissions' dimension scores "
            "side by side: the dimension that should separate them is the one whose "
            "guidance is too coarse."
        )
        lines.append("")

    if not inversions and not collapsed:
        lines += ["Ordering: the system ranked every within-exercise pair as you did.", ""]

    lines += ["VERDICT", "-" * 78]
    if round_.gate_passed and not inversions and not collapsed:
        lines += [
            f"Gate PASSED on {round_.scored} item(s): every letter within "
            f"{GATE_MAX_STEPS} step, no ordering failures and no collapsed pairs.",
            "The rubric is calibrated well enough to author more exercises against.",
        ]
    else:
        lines.append("Gate NOT passed. What to change, in this order:")
        if inversions:
            lines.append(
                "  1. Fix the ordering failures first. They are a judgment problem in "
                "the evaluator prompt, not a weights problem."
            )
        if collapsed:
            lines.append(
                f"  1b. Then the {len(collapsed)} collapsed pair(s). A rubric that "
                "cannot separate two submissions you separated easily is not yet "
                "usable for grading, whatever its average error looks like."
            )
        biased, noisy = _dimension_offenders(round_)
        if biased:
            key, total = biased
            lines.append(
                f"  2. {key} carries the largest consistent bias "
                f"({total:+.1f} weighted points, same direction across the round). "
                "Adjust that dimension's guidance in SYSTEM_PROMPT rather than its "
                "weight -- weights change every historical grade."
            )
        if noisy:
            # Reported even when it is the same dimension as the bias above: the
            # offenders filter only returns a dimension here when its spread
            # substantially outruns its net, so the two lines cannot be redundant --
            # and a dimension whose bias is near zero *because* it errs both ways is
            # the single most misleading thing a signed average can hide.
            key, spread = noisy
            lines.append(
                f"  2b. {key} disagrees by {spread:.1f} weighted points in total but "
                "in BOTH directions, so it cancels out of the average above. That is "
                "not a bias to shift, it is an unreliable judgment -- the prompt's "
                f"definition of {key} is probably ambiguous rather than misplaced."
            )
        if abs(round_.mean_signed_steps) > 0.4:
            adjust = "lower" if round_.mean_signed_steps < 0 else "raise"
            lines.append(
                f"  3. A consistent {round_.mean_signed_steps:+.2f}-step offset is an "
                f"anchor problem: {adjust} the 70/85/95 calibration anchors in "
                "SYSTEM_PROMPT. Do not touch the letter cutoffs."
            )
        lines.append("  Then rebuild the round and regrade. Never edit the gates to agree.")

    if round_.ungraded:
        lines += ["", f"Not graded by the system: {', '.join(e.item for e in round_.ungraded)}"]
    if round_.unfilled:
        lines += ["", f"Awaiting your letter: {', '.join(e.item for e in round_.unfilled)}"]

    lines.append("")
    return "\n".join(lines)


def _dimension_offenders(
    round_: Round,
) -> tuple[tuple[str, float] | None, tuple[str, float] | None]:
    """Return the most biased dimension and the noisiest one.

    These are different diagnoses and want different fixes, which is why both are
    computed. A dimension scored 30 too high on one item and 30 too low on another nets
    to zero and would vanish from a signed average, yet it is arguably *more* broken
    than one that is consistently 10 too high: a consistent offset is a calibration
    anchor to move, an inconsistent one means the dimension's definition is ambiguous.

    Returns:
        ``(biased, noisy)``, each ``(dimension, weighted total)`` or ``None``. ``noisy``
        is reported as a sum of magnitudes, and only when its spread materially exceeds
        its own bias.
    """
    signed: dict[str, float] = {}
    absolute: dict[str, float] = {}
    for comparison in round_.comparisons:
        for key, weighted in comparison.weighted_contribution():
            signed[key] = signed.get(key, 0.0) + weighted
            absolute[key] = absolute.get(key, 0.0) + abs(weighted)
    if not signed:
        return None, None

    biased_key = max(signed, key=lambda name: abs(signed[name]))
    biased = (biased_key, signed[biased_key])

    # Only worth reporting when the magnitudes substantially outrun the net, which is
    # what distinguishes cancellation from a plain consistent offset.
    cancelling = {
        key: total for key, total in absolute.items() if total > abs(signed[key]) * 1.5 + 1.0
    }
    if not cancelling:
        return biased, None
    noisy_key = max(cancelling, key=lambda name: cancelling[name])
    return biased, (noisy_key, cancelling[noisy_key])


def archive(round_: Round) -> str:
    """Append this round's comparisons to the accumulated corpus.

    Args:
        round_: The round to record.

    Returns:
        The archive path, as a string.
    """
    payload = {
        "recorded_at": datetime.now(tz=timezone.utc).isoformat(),
        "gate_passed": round_.gate_passed,
        "mean_signed_steps": round_.mean_signed_steps,
        "items": [
            {
                "item": c.entry.item,
                "persona_key": c.entry.persona_key,
                "exercise_slug": c.entry.exercise_slug,
                "human_letter": c.human.letter,
                "human_dimensions": c.human.dimensions,
                "human_comment": c.human.comment,
                "system_letter": c.entry.system_letter,
                "system_score": c.entry.system_score,
                "system_dimensions": c.entry.system_dimensions,
                "predicted_letter": c.entry.predicted_letter,
                "steps": c.steps,
                "applied_caps": c.entry.applied_caps,
                "session_id": c.entry.session_id,
            }
            for c in round_.comparisons
        ],
    }
    return str(store.append_to_archive(payload))
