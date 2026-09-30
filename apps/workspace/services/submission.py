"""Capture a submission and grade it.

Ordering matters: capture is **committed to the database before grading is
attempted**. Grading re-runs a real test suite and then calls an external API, so it
can fail or time out — and when it does, the user's work must already be safely
recorded so a regrade can reuse the exact same bytes rather than re-reading a
directory that may have changed.
"""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from django.db import transaction

from apps.core.exceptions import ClaudeAPIError
from apps.workspace.enums import CheckStatus, ObjectiveStatus
from apps.workspace.models import (
    WorkspaceCheckResult,
    WorkspaceEvent,
    WorkspaceGrade,
    WorkspaceSession,
    WorkspaceSubmission,
)
from apps.workspace.schemas import Baseline, Check
from apps.workspace.services import diff_collector
from apps.workspace.services.check_runner import CheckRunner, CheckRunSummary
from apps.workspace.services.exercise_evaluator import (
    RUBRIC_VERSION,
    get_exercise_evaluator,
    model_name,
)

logger = logging.getLogger(__name__)


def bundle_destination(session: WorkspaceSession) -> Path:
    """Return where a session's git bundle archive is written."""
    return Path(settings.MEDIA_ROOT) / "workspace_bundles" / f"session-{session.pk}.bundle"


def capture(session: WorkspaceSession) -> WorkspaceSubmission:
    """Capture the work in a session's workspace and persist it.

    Never raises for an unusable workspace: a deleted directory yields a submission
    with ``capture_ok=False`` so grading can still proceed on the written notes,
    rather than returning a server error at the moment of submission.

    Args:
        session: The session being submitted.

    Returns:
        The saved :class:`~apps.workspace.models.WorkspaceSubmission`.
    """
    exercise = session.exercise
    spec = exercise.grading_spec or {}
    grading_hints = spec.get("grading", {})

    result = diff_collector.capture(
        session.workspace_path or "",
        session_id=session.pk,
        seed_sha=session.seed_commit_sha,
        extra_excludes=grading_hints.get("diff_exclude"),
        include_full_files=(exercise.focus_paths or []) + ["NOTES.md"],
        bundle_destination=bundle_destination(session),
    )

    submission, _created = WorkspaceSubmission.objects.update_or_create(
        session=session,
        defaults={
            "capture_ok": result.ok,
            "capture_error": result.error,
            "snapshot_ref": result.snapshot_ref,
            "snapshot_sha": result.snapshot_sha,
            "diff_text": result.diff_text,
            "diff_numstat": [
                {"path": c.path, "added": c.added, "deleted": c.deleted, "status": c.status}
                for c in result.numstat
            ],
            "full_files": result.full_files,
            "files_changed": result.files_changed,
            "lines_added": result.lines_added,
            "lines_deleted": result.lines_deleted,
            "git_log": result.git_log,
            "user_commit_count": result.user_commit_count,
            "branches": result.branches,
            "porcelain_status": result.porcelain_status,
            "untracked_paths": result.untracked_paths,
            "bundle_path": result.bundle_path,
            "capture_bytes": len(result.diff_text or ""),
        },
    )
    logger.info(
        "captured session %s: ok=%s files=%d commits=%d",
        session.pk,
        result.ok,
        submission.files_changed,
        submission.user_commit_count,
    )
    return submission


def _checks_for(exercise) -> list[Check]:
    """Rebuild the authored check objects from the stored grading spec.

    Protected-file hashes recorded at scaffold time are injected into the
    ``file_unchanged`` check here, which is what gives tamper detection something to
    compare against.
    """
    spec = exercise.grading_spec or {}
    protected = spec.get("protected_hashes", {})
    checks: list[Check] = []
    for raw in spec.get("checks", []):
        check = Check.model_validate(raw)
        if check.kind == "file_unchanged" and protected:
            check = check.model_copy(update={"expect": {"hashes": protected}})
        checks.append(check)
    return checks


def run_checks(session: WorkspaceSession, submission: WorkspaceSubmission) -> CheckRunSummary:
    """Run the exercise's objective checks and persist each outcome.

    Args:
        session: The session being graded.
        submission: The captured submission the results attach to.

    Returns:
        The :class:`CheckRunSummary`.
    """
    exercise = session.exercise
    spec = exercise.grading_spec or {}
    baseline = Baseline.model_validate(spec.get("baseline", {}))
    checks = _checks_for(exercise)

    if not submission.capture_ok or not session.workspace_path:
        summary = CheckRunSummary()
        summary.notes.append(
            "Checks were not run because the workspace could not be read. The "
            "objective portion of this grade is indeterminate."
        )
        return summary

    runner = CheckRunner(
        Path(session.workspace_path),
        compose_project=session.compose_project,
        baseline=baseline,
        use_container=bool(session.compose_project),
    )
    summary = runner.run_all(checks)

    WorkspaceCheckResult.objects.filter(submission=submission).delete()
    WorkspaceCheckResult.objects.bulk_create(
        [
            WorkspaceCheckResult(
                submission=submission,
                check_id=outcome.check_id,
                kind=outcome.kind,
                status=outcome.status,
                passed=outcome.passed,
                weight=outcome.weight,
                required=outcome.required,
                stretch=outcome.stretch,
                expected=outcome.expected,
                actual=outcome.actual,
                description=outcome.description,
                duration_ms=outcome.duration_ms,
                output=outcome.output,
            )
            for outcome in summary.outcomes
        ]
    )
    logger.info(
        "checks for session %s: %d/%d required passed, status=%s",
        session.pk,
        summary.required_passed_count,
        len(summary.required_outcomes),
        summary.objective_status,
    )
    return summary


def grade(session: WorkspaceSession, submission: WorkspaceSubmission) -> WorkspaceGrade:
    """Run the checks, evaluate, and persist a grade.

    Args:
        session: The session being graded.
        submission: The captured submission.

    Returns:
        The saved :class:`~apps.workspace.models.WorkspaceGrade`.

    Raises:
        ClaudeAPIError: If neither objective checks nor model review could produce
            any signal. Deliberately not swallowed: a letter computed from nothing
            is worse than no letter at all.
    """
    summary = run_checks(session, submission)
    bundle = get_exercise_evaluator().evaluate(session, submission, summary)
    outcome = bundle.outcome
    evaluation = bundle.evaluation

    runner_log = "\n".join(
        f"$ {outcome_.check_id}: {outcome_.status}" for outcome_ in summary.outcomes
    )

    grade_row, _created = WorkspaceGrade.objects.update_or_create(
        session=session,
        defaults={
            "overall_score": outcome.score,
            "base_score": outcome.base_score,
            "letter_grade": outcome.letter,
            "uncapped_letter": outcome.uncapped_letter,
            "grade_points": outcome.grade_points,
            "speed_bonus": outcome.speed_bonus,
            "dimension_scores": {
                "correctness": bundle.dimensions.correctness,
                "engineering": bundle.dimensions.engineering,
                "documentation": bundle.dimensions.documentation,
                "completeness": bundle.dimensions.completeness,
            },
            "documentation_breakdown": bundle.documentation_breakdown,
            "applied_caps": list(outcome.applied_caps),
            "applied_deductions": bundle.deductions,
            "objective_status": summary.objective_status,
            "evaluation_degraded": bundle.degraded,
            "summary_feedback": (
                evaluation.summary_feedback
                if evaluation
                else "Automated checks only; AI review was unavailable, so this grade is provisional."
            ),
            "detailed_feedback": evaluation.detailed_feedback if evaluation else "",
            "strengths": evaluation.strengths if evaluation else [],
            "areas_for_improvement": evaluation.areas_for_improvement if evaluation else [],
            "what_a_senior_would_have_done": (
                evaluation.what_a_senior_would_have_done if evaluation else ""
            ),
            "root_cause_summary": evaluation.root_cause_summary if evaluation else "",
            "symptom_patch_suspected": (
                evaluation.symptom_patch_suspected if evaluation else False
            ),
            "rubric_version": RUBRIC_VERSION,
            "model_used": model_name() if evaluation else "",
            "grading_log": runner_log,
            "grading_error": bundle.error,
        },
    )

    submission.prompt_char_count = bundle.prompt_chars
    submission.sections_truncated = bundle.sections_truncated
    submission.truncated = bool(bundle.sections_truncated)
    submission.truncation_report = {"sections": bundle.sections_truncated}
    submission.save(
        update_fields=[
            "prompt_char_count",
            "sections_truncated",
            "truncated",
            "truncation_report",
        ]
    )

    WorkspaceEvent.log(
        session,
        WorkspaceEvent.Kind.GRADED,
        letter=outcome.letter,
        score=outcome.score,
        caps=list(outcome.applied_caps),
        degraded=bundle.degraded,
    )
    return grade_row


def capture_and_grade(
    session: WorkspaceSession, *, end_reason: str | None = None
) -> WorkspaceGrade | None:
    """Capture a session's work, end it, and grade it.

    The single entry point used by the submit view, the regrade view and the reaper.

    Args:
        session: The session to finish.
        end_reason: Why it ended; defaults to a normal submission.

    Returns:
        The grade, or ``None`` if grading could not be attempted at all. In that case
        the submission is still saved and the session is left in ``GRADING`` so a
        retry is possible.
    """
    reason = end_reason or WorkspaceSession.EndReason.SUBMITTED

    with transaction.atomic():
        submission = capture(session)
        session.submitted_at = session.submitted_at or _now()
        session.status = WorkspaceSession.Status.GRADING
        session.end_reason = reason
        session.save(update_fields=["submitted_at", "status", "end_reason"])

    WorkspaceEvent.log(session, WorkspaceEvent.Kind.SUBMITTED, reason=reason)

    try:
        grade_row = grade(session, submission)
    except ClaudeAPIError as exc:
        logger.warning("grading unavailable for session %s: %s", session.pk, exc)
        WorkspaceEvent.log(session, WorkspaceEvent.Kind.GRADE_FAILED, error=str(exc))
        # Left in GRADING on purpose: the work is saved and a regrade can retry.
        return None
    except Exception as exc:  # noqa: BLE001 - never lose the submission
        logger.exception("unexpected grading failure for session %s", session.pk)
        WorkspaceEvent.log(session, WorkspaceEvent.Kind.GRADE_FAILED, error=str(exc))
        return None

    session.end_session(reason)
    return grade_row


def _now():
    """Return the current time. Indirected so tests can freeze it."""
    from django.utils import timezone

    return timezone.now()


def status_payload(session: WorkspaceSession) -> dict:
    """Build the JSON the results page polls while grading runs.

    Args:
        session: The session being graded.

    Returns:
        A dict describing progress.
    """
    grade_row = getattr(session, "grade", None)
    return {
        "status": session.status,
        "graded": grade_row is not None,
        "letter": grade_row.letter_grade if grade_row else "",
        "score": grade_row.overall_score if grade_row else None,
        "degraded": grade_row.evaluation_degraded if grade_row else False,
        "objective_status": (
            grade_row.objective_status if grade_row else ObjectiveStatus.INDETERMINATE
        ),
        "checks": [
            {
                "id": row.check_id,
                "status": row.status,
                "passed": row.passed,
                "required": row.required,
                "stretch": row.stretch,
                "description": row.description,
            }
            for row in (
                session.submission.check_results.all() if hasattr(session, "submission") else []
            )
        ],
        "all_checks_ran": (
            all(
                row.status in {CheckStatus.PASSED, CheckStatus.FAILED}
                for row in session.submission.check_results.all()
            )
            if hasattr(session, "submission")
            else False
        ),
    }
