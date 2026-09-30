"""Tests for the server-authoritative workspace timer.

The behaviour these pin down is the reason this mode does not reuse
``apps/coding``'s countdown, which is seeded from a *duration* in the template and
therefore hands out a fresh clock on every page reload.
"""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from freezegun import freeze_time

from apps.workspace.enums import BaseApp, Difficulty, ExerciseType
from apps.workspace.models import WorkspaceExercise, WorkspaceSession

pytestmark = pytest.mark.django_db

START = "2026-03-01 12:00:00"


@pytest.fixture
def exercise(db):
    """A 30-minute intermediate exercise."""
    return WorkspaceExercise.objects.create(
        exercise_number=1,
        slug="ex-001-stale-cache",
        title="SEV-2: order totals are stale after a refund",
        exercise_type=ExerciseType.CRITICAL_BUG,
        base_app=BaseApp.TENANTSAAS,
        difficulty=Difficulty.INTERMEDIATE,
        defect_class="cache_key_collision",
        brief_md="Refunds are not invalidating the cached order total.",
        definition_of_done=["R1: the failing test passes"],
        time_limit_seconds=30 * 60,
        expected_time_minutes=20,
        protected_paths=["tests/**"],
    )


@pytest.fixture
def session(db, user, exercise):
    """A session that has been scaffolded but whose clock has not started."""
    return WorkspaceSession.objects.create(
        user=user,
        exercise=exercise,
        exercise_type=exercise.exercise_type,
        difficulty=exercise.difficulty,
        time_limit_seconds=exercise.time_limit_seconds,
        status=WorkspaceSession.Status.READY,
    )


# ---------------------------------------------------------------------------
# The clock does not start at row creation
# ---------------------------------------------------------------------------


def test_a_ready_session_has_no_deadline_yet(session):
    """Scaffolding and container bring-up must not consume the time box."""
    assert session.started_at is None
    assert session.expires_at is None
    assert session.time_remaining_seconds == 0
    assert not session.is_time_up


def test_is_time_up_is_false_before_the_clock_starts(session):
    """A null deadline must not read as expired, or a ready session would 404."""
    assert session.expires_at is None
    assert session.is_time_up is False
    assert session.is_past_grace is False


def test_begin_sets_both_timestamps_and_status(session):
    with freeze_time(START):
        session.begin()

    session.refresh_from_db()
    assert session.status == WorkspaceSession.Status.IN_PROGRESS
    assert session.started_at is not None
    assert session.expires_at == session.started_at + timedelta(seconds=30 * 60)


def test_begin_accepts_an_explicit_moment(session):
    moment = timezone.now() - timedelta(minutes=5)
    session.begin(now=moment)
    assert session.started_at == moment
    assert session.expires_at == moment + timedelta(minutes=30)


# ---------------------------------------------------------------------------
# Counting down
# ---------------------------------------------------------------------------


def test_remaining_time_counts_down(session):
    with freeze_time(START) as frozen:
        session.begin()
        assert session.time_remaining_seconds == 1800

        frozen.tick(delta=timedelta(minutes=10))
        assert session.time_remaining_seconds == 1200

        frozen.tick(delta=timedelta(minutes=19, seconds=59))
        assert session.time_remaining_seconds == 1


def test_remaining_time_floors_at_zero(session):
    with freeze_time(START) as frozen:
        session.begin()
        frozen.tick(delta=timedelta(hours=5))
        assert session.time_remaining_seconds == 0


def test_reloading_the_page_does_not_reset_the_clock(session):
    """The bug in apps/coding: its countdown restarts from full on every reload.

    Here the deadline is a database row, so re-reading the session mid-attempt
    reports less time, not a fresh allocation.
    """
    with freeze_time(START) as frozen:
        session.begin()
        frozen.tick(delta=timedelta(minutes=12))

        reloaded = WorkspaceSession.objects.get(pk=session.pk)
        assert reloaded.time_remaining_seconds == 1080


def test_closing_the_tab_does_not_pause_the_clock(session):
    """Nothing client-side participates in enforcement."""
    with freeze_time(START) as frozen:
        session.begin()
        frozen.tick(delta=timedelta(minutes=31))
        reloaded = WorkspaceSession.objects.get(pk=session.pk)
        assert reloaded.is_time_up
        assert reloaded.time_remaining_seconds == 0


# ---------------------------------------------------------------------------
# is_time_up boundary
# ---------------------------------------------------------------------------


def test_is_time_up_flips_exactly_at_the_deadline(session):
    with freeze_time(START) as frozen:
        session.begin()
        frozen.tick(delta=timedelta(seconds=1799))
        assert not session.is_time_up

        frozen.tick(delta=timedelta(seconds=1))
        assert session.is_time_up


def test_is_time_up_is_independent_of_status(session):
    """The deliberate divergence from apps/lightning.

    Lightning's ``is_time_up`` returns True for an already-completed session,
    because it is derived from a remaining-time property that returns 0 unless the
    session is in progress. That forces every caller to write
    ``is_time_up and status == IN_PROGRESS``. Anchoring on the deadline keeps the
    two questions separate: "has the bell rung" and "is this session running".
    """
    with freeze_time(START) as frozen:
        session.begin()
        frozen.tick(delta=timedelta(minutes=5))
        session.end_session(WorkspaceSession.EndReason.SUBMITTED)

        # Completed well inside the limit: the bell has NOT rung.
        assert session.status == WorkspaceSession.Status.COMPLETED
        assert session.time_remaining_seconds == 0
        assert not session.is_time_up


def test_a_completed_session_reports_no_remaining_time(session):
    with freeze_time(START):
        session.begin()
        session.end_session(WorkspaceSession.EndReason.SUBMITTED)
    assert session.time_remaining_seconds == 0


# ---------------------------------------------------------------------------
# Submit grace window
# ---------------------------------------------------------------------------


def test_grace_window_accepts_a_submit_just_after_the_bell(session, settings):
    """A submit fired at T-2s whose capture takes 6s must not be rejected."""
    assert settings.WORKSPACE_SUBMIT_GRACE_SECONDS == 30
    with freeze_time(START) as frozen:
        session.begin()
        frozen.tick(delta=timedelta(seconds=1800 + 10))
        assert session.is_time_up
        assert not session.is_past_grace


def test_grace_window_closes_at_its_boundary(session):
    with freeze_time(START) as frozen:
        session.begin()
        frozen.tick(delta=timedelta(seconds=1800 + 29))
        assert not session.is_past_grace

        frozen.tick(delta=timedelta(seconds=1))
        assert session.is_past_grace


# ---------------------------------------------------------------------------
# Elapsed time and the fraction used (feeds the A+ gate and speed bonus)
# ---------------------------------------------------------------------------


def test_elapsed_seconds_is_zero_before_starting(session):
    assert session.elapsed_seconds == 0


def test_elapsed_and_fraction_track_the_time_box(session):
    with freeze_time(START) as frozen:
        session.begin()
        frozen.tick(delta=timedelta(minutes=15))
        assert session.elapsed_seconds == 900
        assert session.fraction_time_used == pytest.approx(0.5)
        assert session.time_used_percentage == 50


def test_elapsed_freezes_once_submitted(session):
    """Elapsed time feeds the speed bonus, so it must stop at submit."""
    with freeze_time(START) as frozen:
        session.begin()
        frozen.tick(delta=timedelta(minutes=10))
        session.submitted_at = timezone.now()
        session.save(update_fields=["submitted_at"])

        frozen.tick(delta=timedelta(minutes=45))
        assert session.elapsed_seconds == 600
        assert session.fraction_time_used == pytest.approx(1 / 3)


def test_fraction_time_used_is_clamped_past_the_deadline(session):
    with freeze_time(START) as frozen:
        session.begin()
        frozen.tick(delta=timedelta(hours=3))
        assert session.fraction_time_used == 1.0
        assert session.time_used_percentage == 100


# ---------------------------------------------------------------------------
# end_session
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reason", "expected_status"),
    [
        (WorkspaceSession.EndReason.SUBMITTED, WorkspaceSession.Status.COMPLETED),
        (WorkspaceSession.EndReason.TIMED_OUT, WorkspaceSession.Status.TIMED_OUT),
        (WorkspaceSession.EndReason.REAPED, WorkspaceSession.Status.TIMED_OUT),
        (WorkspaceSession.EndReason.ABANDONED, WorkspaceSession.Status.ABANDONED),
        (WorkspaceSession.EndReason.FAILED, WorkspaceSession.Status.FAILED),
    ],
)
def test_end_session_maps_reason_to_status(session, reason, expected_status):
    session.begin()
    session.end_session(reason)
    session.refresh_from_db()
    assert session.status == expected_status
    assert session.end_reason == reason
    assert session.completed_at is not None


def test_a_reaped_session_is_distinguishable_from_a_user_timeout(session):
    """Both are timed out, but end_reason records which, for the audit trail."""
    session.begin()
    session.end_session(WorkspaceSession.EndReason.REAPED)
    assert session.status == WorkspaceSession.Status.TIMED_OUT
    assert session.end_reason == WorkspaceSession.EndReason.REAPED


# ---------------------------------------------------------------------------
# Active-status bookkeeping and the uniqueness constraint
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [
        WorkspaceSession.Status.SCAFFOLDING,
        WorkspaceSession.Status.READY,
        WorkspaceSession.Status.IN_PROGRESS,
        WorkspaceSession.Status.GRADING,
    ],
)
def test_pre_terminal_statuses_are_active(session, status):
    """An active session still owns its directory, so cleanup must skip it."""
    session.status = status
    assert session.is_active


@pytest.mark.parametrize(
    "status",
    [
        WorkspaceSession.Status.COMPLETED,
        WorkspaceSession.Status.TIMED_OUT,
        WorkspaceSession.Status.ABANDONED,
        WorkspaceSession.Status.FAILED,
    ],
)
def test_terminal_statuses_are_not_active(session, status):
    session.status = status
    assert not session.is_active


def test_two_active_sessions_on_one_exercise_are_rejected(user, exercise, session):
    """Both would scaffold into the same directory."""
    with pytest.raises(IntegrityError), transaction.atomic():
        WorkspaceSession.objects.create(
            user=user,
            exercise=exercise,
            exercise_type=exercise.exercise_type,
            difficulty=exercise.difficulty,
            time_limit_seconds=exercise.time_limit_seconds,
            status=WorkspaceSession.Status.IN_PROGRESS,
        )


def test_a_second_attempt_is_allowed_once_the_first_finishes(user, exercise, session):
    """Retrying an exercise must stay possible."""
    session.begin()
    session.end_session(WorkspaceSession.EndReason.SUBMITTED)

    retry = WorkspaceSession.objects.create(
        user=user,
        exercise=exercise,
        exercise_type=exercise.exercise_type,
        difficulty=exercise.difficulty,
        time_limit_seconds=exercise.time_limit_seconds,
        status=WorkspaceSession.Status.READY,
    )
    assert retry.pk != session.pk


def test_different_users_can_work_the_same_exercise_concurrently(
    user, admin_user, exercise, session
):
    other = WorkspaceSession.objects.create(
        user=admin_user,
        exercise=exercise,
        exercise_type=exercise.exercise_type,
        difficulty=exercise.difficulty,
        time_limit_seconds=exercise.time_limit_seconds,
        status=WorkspaceSession.Status.IN_PROGRESS,
    )
    assert other.pk != session.pk


# ---------------------------------------------------------------------------
# The 20-60 minute bound
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seconds", [0, 60, 19 * 60, 61 * 60, 120 * 60])
def test_time_limits_outside_the_bound_are_rejected(exercise, seconds):
    """Model-level validation, so a bad fixture fails loudly rather than silently."""
    exercise.time_limit_seconds = seconds
    with pytest.raises(ValidationError) as excinfo:
        exercise.full_clean()
    assert "time_limit_seconds" in excinfo.value.message_dict


@pytest.mark.parametrize("minutes", [20, 30, 45, 60])
def test_time_limits_inside_the_bound_are_accepted(exercise, minutes):
    exercise.time_limit_seconds = minutes * 60
    exercise.full_clean()


def test_expected_time_is_reported_in_minutes(exercise):
    assert exercise.time_limit_minutes == 30
