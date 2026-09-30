"""Background tasks for workspace mode.

Grading runs here rather than inside the HTTP request, because it re-runs the
exercise's real test suite, may run a benchmark, and then calls the Claude API --
60 to 180 seconds in total. ``apps/coding`` evaluates synchronously, which is fine
for a single function executed in a sandbox but would leave this mode's submit
request hanging.
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.workspace.models import WorkspaceSession

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=1, default_retry_delay=30, ignore_result=True)
def grade_submission(self, session_id: int, end_reason: str | None = None) -> dict:
    """Capture and grade a session's work.

    Args:
        session_id: Primary key of the session to grade.
        end_reason: Why the attempt ended; defaults to a normal submission.

    Returns:
        A small summary dict, for the task result backend.
    """
    # Imported lazily so importing this module never pulls in the grading stack.
    from apps.workspace.services import submission as submission_service

    try:
        session = WorkspaceSession.objects.select_related("exercise", "user").get(pk=session_id)
    except WorkspaceSession.DoesNotExist:
        logger.warning("grade_submission: session %s no longer exists", session_id)
        return {"session_id": session_id, "graded": False, "reason": "missing"}

    grade = submission_service.capture_and_grade(session, end_reason=end_reason)
    if grade is None:
        return {"session_id": session_id, "graded": False, "reason": "grading_unavailable"}

    return {
        "session_id": session_id,
        "graded": True,
        "letter": grade.letter_grade,
        "score": grade.overall_score,
    }


@shared_task
def reap_stale_sessions() -> dict:
    """Close out sessions whose deadline has passed without a submission.

    Safe to run from Celery beat or cron. The deadline lives in the database, so it
    is honoured whether or not a browser ever comes back.
    """
    from apps.workspace.services import reaper

    result = reaper.reap_stale_sessions()
    logger.info(
        "reaped %d overdue and abandoned %d stalled session(s)",
        len(result["reaped"]),
        len(result["abandoned"]),
    )
    return result
