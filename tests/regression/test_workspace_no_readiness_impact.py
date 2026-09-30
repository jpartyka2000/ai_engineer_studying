"""Locks in the decision to keep workspace mode out of readiness scoring.

``ReadinessCalculatorService.MODE_WEIGHTS`` must sum to 1.0, so adding a fifth mode
would silently rescale every historical readiness number. And one workspace exercise
spans FastAPI, Docker, Postgres and pytest at once, so attributing it to a single
subject would misreport both the subject and the mode.

These are regression tests rather than unit tests: they exist to fail loudly if
someone later wires the two together without reconsidering the weights.
"""

import inspect

import pytest

from apps.readiness.services.readiness_service import ReadinessCalculatorService
from apps.workspace.enums import BaseApp, Difficulty, ExerciseType
from apps.workspace.models import WorkspaceExercise, WorkspaceSession

pytestmark = pytest.mark.django_db


def test_mode_weights_still_sum_to_one():
    total = sum(ReadinessCalculatorService.MODE_WEIGHTS.values())
    assert total == pytest.approx(1.0), (
        "MODE_WEIGHTS must sum to 1.0; adding a mode requires rebalancing the others, "
        "which changes every historical readiness score."
    )


def test_workspace_is_not_a_readiness_mode():
    assert "workspace" not in ReadinessCalculatorService.MODE_WEIGHTS
    assert set(ReadinessCalculatorService.MODE_WEIGHTS) == {
        "coding",
        "exam",
        "argument",
        "lightning",
    }


def test_readiness_does_not_reference_workspace_models():
    """Guards against a future aggregate quietly sweeping in workspace rows."""
    from apps.readiness.services import readiness_service

    source = inspect.getsource(readiness_service)
    assert "WorkspaceSession" not in source
    assert "apps.workspace" not in source


def test_completing_an_exercise_does_not_change_a_readiness_score(user):
    """The behavioural version of the checks above."""
    service = ReadinessCalculatorService()
    before = service.calculate_readiness(user)

    exercise = WorkspaceExercise.objects.create(
        exercise_number=901,
        slug="ex-901-regression-probe",
        title="Probe",
        exercise_type=ExerciseType.CRITICAL_BUG,
        base_app=BaseApp.TENANTSAAS,
        difficulty=Difficulty.INTERMEDIATE,
        defect_class="probe",
        brief_md="probe",
        definition_of_done=["R1: passes"],
        time_limit_seconds=20 * 60,
        expected_time_minutes=14,
        protected_paths=["tests/**"],
    )
    session = WorkspaceSession.objects.create(
        user=user,
        exercise=exercise,
        exercise_type=exercise.exercise_type,
        difficulty=exercise.difficulty,
        time_limit_seconds=exercise.time_limit_seconds,
    )
    session.begin()
    session.end_session(WorkspaceSession.EndReason.SUBMITTED)

    after = ReadinessCalculatorService().calculate_readiness(user)
    assert after.overall_score == before.overall_score


def test_subject_has_no_workspace_support_flag():
    """Workspace mode is top-level, not subject-scoped.

    If a ``supports_workspace`` field appears later, the catalog and this decision
    need revisiting together rather than drifting apart.
    """
    from apps.subjects.models import Subject

    field_names = {field.name for field in Subject._meta.get_fields()}
    assert "supports_workspace" not in field_names


def test_subject_stats_do_not_aggregate_workspace_sessions():
    """The subject dashboard must keep meaning "performance on this subject"."""
    from apps.subjects import views

    source = inspect.getsource(views)
    assert "WorkspaceSession" not in source
