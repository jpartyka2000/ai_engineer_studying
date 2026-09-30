"""Grade a submission: objective checks reconciled with model judgment.

Two rules shape everything here.

**The model never produces the final number.** It scores four dimensions; the
weighted score and the letter are computed in Python by
:mod:`apps.workspace.grading`. ``apps/coding`` asks its model for an
``overall_score`` and then silently recomputes it whenever tests ran, leaving a dead
field that disagrees with the stored value.

**Objective checks can only lower the model's correctness score, never raise it.**
The reconciliation is ``min(objective, model)``, so green tests plus an obviously
cheating implementation still scores low, while a red test run can never be talked
up.
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from typing import Final

from django.conf import settings

from apps.core.exceptions import ClaudeAPIError
from apps.core.services.claude_service import get_claude_service
from apps.workspace.enums import ExerciseType, ObjectiveStatus
from apps.workspace.grading import (
    DimensionScores,
    GateSignals,
    apply_gates,
)
from apps.workspace.schemas import ExerciseEvaluation
from apps.workspace.services.check_runner import CheckRunSummary
from apps.workspace.services.prompt_budget import build_grading_prompt

logger = logging.getLogger(__name__)

RUBRIC_VERSION: Final[str] = "2026.03-1"

#: Score imputed for dimensions that cannot be estimated without model judgment.
#: Matches the "competent junior" calibration anchor in the system prompt, and is
#: always surfaced as provisional rather than presented as a real assessment.
IMPUTED_SCORE: Final[int] = 70

SYSTEM_PROMPT: Final[str] = """\
You are a staff-level engineer conducting a post-mortem review of a time-boxed change \
made to a production codebase by a mid-level engineer.

Score each dimension 0-100, independently.

1. CORRECTNESS -- is the stated problem actually solved, at the root cause?
   Automated acceptance checks have already run; their results appear in the prompt \
and are AUTHORITATIVE for whether the problem is solved. Your job on this dimension \
is to judge whether the fix is GENUINELY correct or merely satisfies the tests: \
hardcoded values, special-cased inputs, weakened logic, a feature quietly disabled, \
or filtering after the fact instead of at the source. If the tests pass but the \
implementation is a cheat, score LOW and set symptom_patch_suspected to true.

2. ENGINEERING QUALITY -- root cause versus symptom; a minimal, surgical diff; \
following the repository's existing conventions and layering; no collateral damage; \
sensible error handling; tests added or updated; sane commit granularity.

3. DOCUMENTATION AND EXPLANATION -- score all five sub-dimensions in \
documentation_breakdown. An absent or unfilled NOTES.md is a severe deduction. \
Comment NOISE that merely restates the code is not documentation and must not raise \
this score.

4. COMPLETENESS -- every item in the Definition of Done, including the secondary \
asks, not just the headline fix.

CALIBRATION: 70 is a competent junior. 85 is solid mid-level. 95 and above is what a \
staff engineer would ship. Do not inflate. A change that works but is undocumented \
should score around 90 on correctness and around 30 on documentation.

TIME: the prompt states how long was available and how much was used. Calibrate SCOPE \
expectations to the time box -- do not penalise a well-diagnosed partial fix for being \
partial. Do NOT extend that leniency to documentation: writing three sentences of \
explanation is never outside the time budget.

Be concrete. Name files and functions. In what_a_senior_would_have_done, say what you \
would have done differently, so the engineer learns something even when they passed.

You must respond with valid JSON only."""

#: Appended to the system prompt per exercise type. One prompt parameterised by this
#: dict, rather than the four near-duplicate prompts in
#: ``apps/coding/services/code_evaluator.py`` -- where the documentation bullet was
#: lost from three of the four copies.
TYPE_GUIDANCE: Final[dict[str, str]] = {
    ExerciseType.CRITICAL_BUG: (
        "This was an urgent bug fix. Weigh whether they found the root cause or "
        "patched the symptom, and whether the fix generalises beyond the reported "
        "case. A narrow fix that leaves the same class of defect reachable is a "
        "symptom patch."
    ),
    ExerciseType.LATENCY: (
        "This was a performance fix. The benchmark reports work counts (queries, "
        "calls, rows) rather than wall-clock time. Check they reduced the work done "
        "rather than hiding it behind a cache, and that correctness is intact."
    ),
    ExerciseType.ML_DEPLOY: (
        "This was a model-serving task. Weigh input validation, the feature "
        "pipeline's train/serve consistency, model versioning, and error handling on "
        "malformed input -- not model accuracy, which is fixed."
    ),
    ExerciseType.ETL_PIPELINE: (
        "This was a data pipeline task. Idempotency matters most: running twice must "
        "not double-count. Also weigh schema drift, late-arriving data and data "
        "quality gates."
    ),
    ExerciseType.GENAI_CHATBOT: (
        "This was a generative-AI task against a recorded model client, so responses "
        "are deterministic. Weigh retrieval, routing, prompt assembly and guardrails "
        "-- not model quality."
    ),
    ExerciseType.EDA_LIBRARY: (
        "This was library work. Weigh the public API's shape, docstrings with "
        "examples, edge-case handling on messy input, and test coverage of the new "
        "surface."
    ),
    ExerciseType.TENANT_ISOLATION: (
        "This was a security fix. The decisive question is whether the fix FAILS "
        "CLOSED: an unrecognised input must raise rather than be skipped. Filtering "
        "rows after the query has run is NOT a fix -- the data has already crossed "
        "the trust boundary. Weigh whether they fixed the class of bug or one "
        "instance of it."
    ),
    ExerciseType.EVAL_FRAMEWORK: (
        "This was evaluation-harness work. Weigh whether the metrics are correct on "
        "known-answer fixtures, whether the harness is reproducible, and whether it "
        "would catch a regression."
    ),
    ExerciseType.ANALYTICS_FEATURES: (
        "This was statistical feature work. Weigh numerical correctness against the "
        "golden constants, correct handling of small samples and division by zero, "
        "and whether the statistics chosen actually answer the question asked."
    ),
    ExerciseType.CICD_PIPELINE: (
        "This was pipeline repair. Both the workflow file and its executable mirror "
        "must be fixed -- repairing only the script is incomplete. For a flaky test, "
        "weigh whether they addressed the underlying nondeterminism or merely "
        "retried it."
    ),
}


@dataclass
class GradeOutcomeBundle:
    """Everything needed to persist a grade."""

    dimensions: DimensionScores
    outcome: object
    evaluation: ExerciseEvaluation | None = None
    degraded: bool = False
    error: str = ""
    deductions: list[str] = field(default_factory=list)
    documentation_breakdown: dict[str, int] = field(default_factory=dict)
    prompt_chars: int = 0
    sections_truncated: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Objective deductions
# ---------------------------------------------------------------------------


def engineering_deductions(
    *, summary: CheckRunSummary, submission, hints_used: int
) -> tuple[int, list[str]]:
    """Compute objective deductions against engineering quality.

    Applied in Python rather than trusted to the model, because each is mechanically
    detectable and should be consistent across submissions.

    Returns:
        ``(total_points, reasons)``.
    """
    total = 0
    reasons: list[str] = []

    if summary.regressions:
        total += 15
        reasons.append(f"-15 broke {len(summary.regressions)} previously-passing test(s)")
    if submission.user_commit_count == 0 and submission.files_changed > 0:
        total += 10
        reasons.append("-10 no commits: all work left uncommitted in a dirty tree")
    if hints_used > 1:
        extra = hints_used - 1
        total += 5 * extra
        reasons.append(f"-{5 * extra} used {hints_used} hints")
    return total, reasons


# ---------------------------------------------------------------------------
# Documentation heuristic (used only when model review is unavailable)
# ---------------------------------------------------------------------------

STUB_MARKER = re.compile(r"^\s*<!--.*-->\s*$")


def documentation_heuristic(session, submission) -> int:
    """Estimate a documentation score without model judgment.

    Only used in the degraded path. Documentation gets a heuristic where the other
    dimensions do not, because it has genuine mechanical proxies -- filled headings,
    added comments, docstrings on new functions, real commit messages -- whereas
    "root cause versus symptom patch" has none. Being explicit about which is which
    beats pretending both can be estimated.

    Returns:
        A score from 0 to 100.
    """
    score = 0

    # Filled NOTES.md headings, proportional, worth up to 60.
    notes = session.user_notes or ""
    headings = re.findall(r"^##\s+(.+)$", notes, re.MULTILINE)
    if headings:
        filled = 0
        sections = re.split(r"^##\s+.+$", notes, flags=re.MULTILINE)[1:]
        for body in sections:
            lines = [
                line
                for line in body.strip().splitlines()
                if line.strip() and not STUB_MARKER.match(line)
            ]
            if lines:
                filled += 1
        score += int(60 * filled / max(len(headings), 1))

    # Comments added to changed source, worth up to 15.
    diff = submission.diff_text or ""
    added_comments = sum(
        1 for line in diff.splitlines() if line.startswith("+") and line[1:].strip().startswith("#")
    )
    if added_comments:
        score += min(15, 5 * added_comments)

    # Docstrings on new public functions, worth up to 15.
    documented = undocumented = 0
    for path, content in (submission.full_files or {}).items():
        if not path.endswith(".py"):
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                if ast.get_docstring(node):
                    documented += 1
                else:
                    undocumented += 1
    if documented + undocumented:
        score += int(15 * documented / (documented + undocumented))

    # Commit messages that say something, worth up to 10.
    log = submission.git_log or ""
    subjects = [
        line.strip() for line in log.splitlines() if line.strip() and not line.startswith("---")
    ]
    if subjects:
        meaningful = [s for s in subjects if len(s) > 40 and s.lower() not in {"wip", "fix"}]
        score += int(10 * len(meaningful) / len(subjects))

    return max(0, min(100, score))


# ---------------------------------------------------------------------------
# The evaluator
# ---------------------------------------------------------------------------


class ExerciseEvaluatorService:
    """Turns a submission plus check results into a letter grade."""

    def __init__(self) -> None:
        self.claude = get_claude_service()

    def _system_prompt(self, exercise) -> str:
        """Build the system prompt for an exercise's type."""
        guidance = TYPE_GUIDANCE.get(exercise.exercise_type, "")
        if not guidance:
            return SYSTEM_PROMPT
        return f"{SYSTEM_PROMPT}\n\nFOR THIS KIND OF TASK: {guidance}"

    def _ask_model(self, exercise, prompt_text: str) -> ExerciseEvaluation:
        """Call the model and validate its response.

        Retries once at temperature 0 with the validation error appended, which
        ``apps/coding`` does not do -- a single malformed response should not cost a
        grade.

        Raises:
            ClaudeAPIError: If the call fails, or the response is still invalid after
                the retry.
        """
        system = self._system_prompt(exercise)
        schema_hint = (
            "\n\nRespond with a single JSON object containing exactly these keys: "
            "solved, root_cause_identified, root_cause_summary, symptom_patch_suspected, "
            "correctness{score,feedback}, engineering_quality{score,feedback}, "
            "documentation{score,feedback}, "
            "documentation_breakdown{inline_comments,docstrings,commit_messages,"
            "writeup_notes_md,updated_project_docs}, completeness{score,feedback}, "
            "acceptance_judgments[{criterion_id,met,confidence,rationale}], "
            "stretch_criteria_met[], summary_feedback, detailed_feedback, strengths[], "
            "areas_for_improvement[], what_a_senior_would_have_done."
        )

        response = self.claude.generate_json_completion(
            prompt=prompt_text + schema_hint,
            system_message=system,
            max_tokens=8192,
            temperature=0.2,
        )
        try:
            return ExerciseEvaluation.model_validate(response)
        except Exception as first_error:  # noqa: BLE001 - pydantic ValidationError
            logger.warning("grading response failed validation, retrying at t=0: %s", first_error)
            retry = self.claude.generate_json_completion(
                prompt=(
                    prompt_text
                    + schema_hint
                    + f"\n\nYour previous response was rejected: {first_error}. "
                    "Return only valid JSON matching the keys above."
                ),
                system_message=system,
                max_tokens=8192,
                temperature=0.0,
            )
            try:
                return ExerciseEvaluation.model_validate(retry)
            except Exception as second_error:  # noqa: BLE001
                raise ClaudeAPIError(
                    f"Grading response was invalid twice: {second_error}"
                ) from second_error

    def evaluate(self, session, submission, summary: CheckRunSummary) -> GradeOutcomeBundle:
        """Grade a submission.

        Args:
            session: The :class:`~apps.workspace.models.WorkspaceSession`.
            submission: The captured :class:`~apps.workspace.models.WorkspaceSubmission`.
            summary: Results of the objective checks.

        Returns:
            A :class:`GradeOutcomeBundle` ready to persist.
        """
        exercise = session.exercise
        objective_complete = summary.objective_status == ObjectiveStatus.COMPLETE
        deduction_points, deduction_reasons = engineering_deductions(
            summary=summary, submission=submission, hints_used=session.hints_used
        )

        built = build_grading_prompt(
            exercise=exercise, session=session, submission=submission, check_summary=summary
        )

        evaluation: ExerciseEvaluation | None = None
        degraded = False
        error = ""
        try:
            evaluation = self._ask_model(exercise, built.text)
        except ClaudeAPIError as exc:
            degraded = True
            error = str(exc)
            logger.warning("grading degraded for session %s: %s", session.pk, exc)

        if evaluation is not None:
            correctness = evaluation.correctness.score
            if objective_complete:
                # min(), not an average: the model may lower a green run but can
                # never talk up a red one.
                correctness = min(summary.objective_correctness, correctness)
            engineering = max(0, min(100, evaluation.engineering_quality.score - deduction_points))
            documentation = evaluation.documentation.score
            completeness = evaluation.completeness.score
            breakdown = evaluation.documentation_breakdown.model_dump()
        else:
            if not objective_complete:
                # No objective signal and no model: refuse rather than invent a
                # letter from nothing.
                raise ClaudeAPIError(
                    "Cannot grade: the automated checks could not be run and model "
                    "review is unavailable. Nothing would inform the grade."
                )
            correctness = summary.objective_correctness
            engineering = max(0, IMPUTED_SCORE - deduction_points)
            documentation = documentation_heuristic(session, submission)
            completeness = IMPUTED_SCORE
            breakdown = {}
            deduction_reasons.append(
                "Engineering and completeness are imputed; model review was unavailable."
            )

        dimensions = DimensionScores(
            correctness=correctness,
            engineering=engineering,
            documentation=documentation,
            completeness=completeness,
        )

        signals = GateSignals(
            required_checks_total=len(summary.required_outcomes),
            required_checks_passed=summary.required_passed_count,
            regressions=len(summary.regressions),
            tampering_detected=summary.tampering_detected,
            is_empty_submission=submission.is_empty,
            timed_out=session.end_reason == session.EndReason.TIMED_OUT,
            stretch_checks_passed=summary.stretch_passed_count
            + len(evaluation.stretch_criteria_met if evaluation else []),
            documentation_score=documentation,
            fraction_time_used=session.fraction_time_used,
            exercise_type=exercise.exercise_type,
        )

        return GradeOutcomeBundle(
            dimensions=dimensions,
            outcome=apply_gates(dimensions.weighted(), signals),
            evaluation=evaluation,
            degraded=degraded,
            error=error,
            deductions=deduction_reasons,
            documentation_breakdown=breakdown,
            prompt_chars=built.char_count,
            sections_truncated=built.sections_truncated,
        )


_service: ExerciseEvaluatorService | None = None


def get_exercise_evaluator() -> ExerciseEvaluatorService:
    """Return the shared evaluator instance.

    Matches the ``get_code_evaluator()`` singleton convention used elsewhere.
    """
    global _service  # noqa: PLW0603 - matches the existing service pattern
    if _service is None:
        _service = ExerciseEvaluatorService()
    return _service


def model_name() -> str:
    """Return the configured model identifier, for the audit record."""
    return getattr(settings, "CLAUDE_MODEL", "")
