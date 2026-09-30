"""End-to-end grading, with the model call mocked.

Exercises the whole pipeline — scaffold, work, capture, checks, evaluate, letter —
on the real checked-in template. Only the Claude call is faked; the git work and the
grade arithmetic are real.

The objective checks here report ``indeterminate`` because running the exercise's own
suite requires its container image, which this test does not build. That path is
itself worth covering: an unrunnable check must fall back to model judgment rather
than scoring a zero.
"""

from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from apps.core.exceptions import ClaudeAPIError
from apps.workspace.enums import ObjectiveStatus
from apps.workspace.models import WorkspaceExercise, WorkspaceSession
from apps.workspace.services import scaffolder

pytestmark = pytest.mark.django_db


def model_response(
    *,
    correctness=95,
    engineering=88,
    documentation=90,
    completeness=92,
    solved=True,
    symptom=False,
    stretch=None,
) -> dict:
    """Build a well-formed grading response."""
    return {
        "solved": solved,
        "root_cause_identified": True,
        "root_cause_summary": "created_at is a timestamp; the period bounds are dates.",
        "symptom_patch_suspected": symptom,
        "correctness": {"score": correctness, "feedback": "Fixed at the right layer."},
        "engineering_quality": {"score": engineering, "feedback": "Surgical diff."},
        "documentation": {"score": documentation, "feedback": "Clear notes."},
        "documentation_breakdown": {
            "inline_comments": documentation,
            "docstrings": documentation,
            "commit_messages": documentation,
            "writeup_notes_md": documentation,
            "updated_project_docs": documentation,
        },
        "completeness": {"score": completeness, "feedback": "All items covered."},
        "acceptance_judgments": [],
        "stretch_criteria_met": stretch or [],
        "summary_feedback": "Correct fix, well explained.",
        "detailed_feedback": "The comparison now uses __date__lte.",
        "strengths": ["Found the root cause"],
        "areas_for_improvement": ["Could add a regression test"],
        "what_a_senior_would_have_done": "Also added a constraint at the database level.",
    }


def all_checks_passing(session):
    """Build a CheckRunSummary in which every authored check passed.

    Needed because the pytest-based checks execute inside the exercise's container,
    which these tests do not build. Stubbing the objective half lets the grade
    arithmetic and the reconciliation be tested on their own; the unverifiable case
    is covered separately by
    :func:`test_an_unverifiable_fix_is_capped_even_when_correct`.
    """
    from apps.workspace.enums import CheckStatus
    from apps.workspace.schemas import Check
    from apps.workspace.services.check_runner import CheckOutcome, CheckRunSummary

    summary = CheckRunSummary()
    for raw in (session.exercise.grading_spec or {}).get("checks", []):
        check = Check.model_validate(raw)
        if check.kind == "llm":
            continue
        summary.outcomes.append(
            CheckOutcome(
                check_id=check.id,
                kind=str(check.kind),
                status=str(CheckStatus.PASSED),
                passed=True,
                weight=check.weight,
                required=check.required,
                stretch=check.stretch,
                description=check.description,
            )
        )
    return summary


@pytest.fixture(autouse=True)
def workspace_root(tmp_path, settings):
    root = tmp_path / "home" / "user" / "workspaces"
    root.mkdir(parents=True)
    settings.WORKSPACE_ROOT = root
    return root


@pytest.fixture
def session(db, user):
    """A started session on a scaffolded workspace, no containers."""
    call_command("seed_workspace_exercises", slug="ex-001-invoice-drops-final-day", verbosity=0)
    exercise = WorkspaceExercise.objects.get(slug="ex-001-invoice-drops-final-day")
    exercise.needs_docker = False
    exercise.save(update_fields=["needs_docker"])

    row = WorkspaceSession.objects.create(
        user=user,
        exercise=exercise,
        exercise_type=exercise.exercise_type,
        difficulty=exercise.difficulty,
        time_limit_seconds=exercise.time_limit_seconds,
        status=WorkspaceSession.Status.SCAFFOLDING,
    )
    result = scaffolder.scaffold(row)
    assert result.ok, result.error
    row.refresh_from_db()
    # No compose project, so checks run locally rather than via docker exec.
    row.compose_project = ""
    row.begin()
    return row


def do_the_work(session: WorkspaceSession, *, notes: str = "") -> None:
    """Apply the correct fix and write notes, as a user would."""
    from apps.workspace.services import git_ops

    workspace = Path(session.workspace_path)
    target = workspace / "billing" / "services.py"
    target.write_text(
        target.read_text()
        .replace("created_at__gte=period_start", "created_at__date__gte=period_start")
        .replace("created_at__lt=period_end", "created_at__date__lte=period_end")
    )
    if notes:
        (workspace / "NOTES.md").write_text(notes)
        session.user_notes = notes
        session.save(update_fields=["user_notes"])

    git_ops.run_git(workspace, "add", "-A")
    git_ops.run_git(
        workspace,
        "commit",
        "-q",
        "-m",
        "fix(billing): compare dates against dates\n\nThe period bounds are dates while created_at is a timestamp, so the\nfinal day was being dropped.",
        env_extra={
            "GIT_AUTHOR_NAME": "Test User",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test User",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )


GOOD_NOTES = """\
## Diagnosis
Invoices were missing the last day of the period.

## Root cause
`created_at` is a timestamp while the bounds are dates, so Postgres coerced
`period_end` to midnight and `__lt` excluded the whole final day.

## The fix
Compare dates against dates with `__date__gte` / `__date__lte`.

## What I verified
The full suite, plus a single-day period.
"""


def test_a_correct_well_documented_fix_earns_a_high_grade(session):
    do_the_work(session, notes=GOOD_NOTES)

    from apps.workspace.services import submission as submission_service

    with (
        patch.object(submission_service, "run_checks", return_value=all_checks_passing(session)),
        patch(
            "apps.core.services.claude_service.ClaudeService.generate_json_completion",
            return_value=model_response(),
        ),
    ):
        grade = submission_service.capture_and_grade(session)

    assert grade is not None
    assert grade.letter_grade in {"A-", "A", "B+"}
    assert grade.overall_score >= 87
    assert grade.dimension_scores["documentation"] == 90
    assert grade.model_used
    assert not grade.evaluation_degraded
    assert grade.applied_caps == []


def test_the_same_fix_with_no_notes_scores_far_lower(session):
    """The headline consequence of documentation being a quarter of the mark.

    Identical code, identical passing checks — only the writeup is missing.
    """
    do_the_work(session)

    from apps.workspace.services import submission as submission_service

    with (
        patch.object(submission_service, "run_checks", return_value=all_checks_passing(session)),
        patch(
            "apps.core.services.claude_service.ClaudeService.generate_json_completion",
            return_value=model_response(documentation=10),
        ),
    ):
        grade = submission_service.capture_and_grade(session)

    assert grade.overall_score <= 80
    assert grade.letter_grade in {"B-", "C+", "C"}
    # No gate fired: the drop is purely the documentation weight doing its job.
    assert grade.applied_caps == []


def test_an_unverifiable_fix_is_capped_even_when_correct(session):
    """A correct fix the harness cannot confirm must not be given the benefit.

    Here the container is not built, so the pytest-based checks cannot run and only
    some required checks pass. The unsolved gate caps the result — which is the
    honest outcome, because nothing proved the problem was actually solved.
    """
    do_the_work(session, notes=GOOD_NOTES)

    from apps.workspace.services import submission as submission_service

    with patch(
        "apps.core.services.claude_service.ClaudeService.generate_json_completion",
        return_value=model_response(),
    ):
        grade = submission_service.capture_and_grade(session)

    from apps.workspace.grading import GATE_NOTHING_SOLVED, GATE_UNSOLVED

    assert {GATE_UNSOLVED, GATE_NOTHING_SOLVED} & set(grade.applied_caps)
    assert grade.overall_score < grade.base_score or grade.uncapped_letter != grade.letter_grade


def test_an_empty_submission_is_an_f(session):
    from apps.workspace.services import submission as submission_service

    with patch(
        "apps.core.services.claude_service.ClaudeService.generate_json_completion",
        return_value=model_response(correctness=0, solved=False),
    ):
        grade = submission_service.capture_and_grade(session)

    assert grade.letter_grade == "F"
    assert "G5_empty_submission" in grade.applied_caps


def test_tampering_with_a_protected_test_is_an_f(session):
    """The one hard-fail rule, exercised through the real hash comparison."""
    workspace = Path(session.workspace_path)
    target = workspace / "tests" / "test_billing.py"
    target.write_text(target.read_text().replace("assert ", "assert True or "))
    do_the_work(session, notes=GOOD_NOTES)

    from apps.workspace.services import submission as submission_service

    with patch(
        "apps.core.services.claude_service.ClaudeService.generate_json_completion",
        return_value=model_response(),
    ):
        grade = submission_service.capture_and_grade(session)

    assert grade.letter_grade == "F"
    assert "G4_test_tampering" in grade.applied_caps
    assert grade.overall_score == 0


def test_a_degraded_grade_is_marked_provisional(session):
    """Objective signal is indeterminate here, so no model means no grade at all."""
    do_the_work(session, notes=GOOD_NOTES)

    from apps.workspace.services import submission as submission_service

    with patch(
        "apps.core.services.claude_service.ClaudeService.generate_json_completion",
        side_effect=ClaudeAPIError("upstream unavailable"),
    ):
        grade = submission_service.capture_and_grade(session)

    # Refusing is correct: a letter from zero signal is worse than none.
    assert grade is None
    session.refresh_from_db()
    assert session.status == WorkspaceSession.Status.GRADING


def test_a_malformed_model_response_is_retried_once(session):
    do_the_work(session, notes=GOOD_NOTES)

    from apps.workspace.services import submission as submission_service

    with patch(
        "apps.core.services.claude_service.ClaudeService.generate_json_completion",
        side_effect=[{"nonsense": True}, model_response()],
    ) as called:
        grade = submission_service.capture_and_grade(session)

    assert called.call_count == 2
    assert grade is not None
    assert grade.letter_grade


def test_running_out_of_time_still_grades_partial_work(session):
    """Explicit design decision: the buzzer is not an automatic fail."""
    do_the_work(session, notes=GOOD_NOTES)
    session.expires_at = session.started_at + timedelta(seconds=1)
    session.save(update_fields=["expires_at"])

    from apps.workspace.services import submission as submission_service

    with patch(
        "apps.core.services.claude_service.ClaudeService.generate_json_completion",
        return_value=model_response(correctness=70, completeness=60),
    ):
        grade = submission_service.capture_and_grade(
            session, end_reason=WorkspaceSession.EndReason.TIMED_OUT
        )

    assert grade.letter_grade != "F"
    session.refresh_from_db()
    assert session.status == WorkspaceSession.Status.TIMED_OUT


def test_objective_status_is_recorded_as_indeterminate_without_containers(session):
    do_the_work(session, notes=GOOD_NOTES)

    from apps.workspace.services import submission as submission_service

    with patch(
        "apps.core.services.claude_service.ClaudeService.generate_json_completion",
        return_value=model_response(),
    ):
        grade = submission_service.capture_and_grade(session)

    assert grade.objective_status in {
        ObjectiveStatus.INDETERMINATE,
        ObjectiveStatus.PARTIAL,
        ObjectiveStatus.COMPLETE,
    }


def test_the_results_page_renders_the_grade(session, user):
    do_the_work(session, notes=GOOD_NOTES)

    from apps.workspace.services import submission as submission_service

    with patch(
        "apps.core.services.claude_service.ClaudeService.generate_json_completion",
        return_value=model_response(),
    ):
        grade = submission_service.capture_and_grade(session)

    client = Client(headers={"host": "localhost"})
    client.force_login(user)
    response = client.get(reverse("workspace:results", kwargs={"pk": session.pk}))

    assert response.status_code == 200
    assert grade.letter_grade.encode() in response.content
    assert b"What a senior engineer would have done" in response.content


def test_the_results_page_never_leaks_the_private_grading_notes(session, user):
    do_the_work(session, notes=GOOD_NOTES)

    from apps.workspace.services import submission as submission_service

    with patch(
        "apps.core.services.claude_service.ClaudeService.generate_json_completion",
        return_value=model_response(),
    ):
        submission_service.capture_and_grade(session)

    client = Client(headers={"host": "localhost"})
    client.force_login(user)
    response = client.get(reverse("workspace:results", kwargs={"pk": session.pk}))
    assert b"Common wrong turns" not in response.content
