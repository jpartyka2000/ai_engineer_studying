"""Drive one persona through the real grading pipeline.

Nothing here is a test double. The workspace is scaffolded by the real scaffolder, the
containers really come up, the acceptance checks really run inside them, and the real
model call produces the dimension scores. A calibration result obtained any other way
would be measuring the harness rather than the rubric.

The one thing that *is* simulated is the clock: ``started_at`` is backdated so the
session reports the persona's declared elapsed time. That matters because elapsed time
feeds the prompt's scope expectations, the A+ gate and the speed bonus, and waiting out
a 40-minute time box per persona would make the whole exercise unaffordable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.workspace.calibration.spec import Persona, apply_persona
from apps.workspace.models import WorkspaceExercise, WorkspaceGrade, WorkspaceSession
from apps.workspace.services import docker_env, scaffolder, submission as submission_service
from apps.workspace.services.check_runner import CheckRunner

logger = logging.getLogger(__name__)

#: Sessions are owned by a dedicated account so a calibration round never lands in the
#: real user's progress history or averages.
CALIBRATION_USERNAME = "calibration-bot"

#: Applied to the running container before the persona's edits, because every brief
#: tells the candidate to run it as step two of reproducing the problem.
#:
#: Skipping it is not a harmless shortcut. pytest-django builds and migrates its own
#: test database, so the pytest checks pass either way -- but a benchmark or a
#: management command runs against the *development* database, and against an
#: unmigrated one it dies with "relation does not exist". That surfaced as ex-002's
#: query-count check erroring out for all three personas, capping every one of them at
#: C+ for a reason that had nothing to do with the submission.
SETUP_COMMAND = "python manage.py migrate --noinput"


class CalibrationError(RuntimeError):
    """A persona could not be built or graded."""


@dataclass
class BuildResult:
    """Outcome of building and grading one persona."""

    persona: Persona
    session: WorkspaceSession | None = None
    grade: WorkspaceGrade | None = None
    ok: bool = False
    error: str = ""
    log: list[str] | None = None

    @property
    def letter(self) -> str:
        """The system's letter, or an empty string if grading did not finish."""
        return self.grade.letter_grade if self.grade else ""


def calibration_user():
    """Return (creating if needed) the account calibration sessions belong to."""
    model = get_user_model()
    user, created = model.objects.get_or_create(
        username=CALIBRATION_USERNAME,
        defaults={"is_active": False, "email": "calibration@localhost"},
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
        logger.info("created the calibration user")
    return user


def _close_stale_sessions(exercise: WorkspaceExercise) -> None:
    """Retire any live calibration session on this exercise.

    The model enforces one active session per (user, exercise), and every persona for
    an exercise reuses that pair, so the previous persona's session must be closed
    before the next is created. Marked abandoned rather than deleted: its grade is
    still a legitimate historical record.
    """
    stale = WorkspaceSession.objects.filter(
        user=calibration_user(),
        exercise=exercise,
        status__in=WorkspaceSession.ACTIVE_STATUSES,
    )
    for session in stale:
        session.end_session(WorkspaceSession.EndReason.ABANDONED)
        logger.info("closed stale calibration session %s", session.pk)


def build(persona: Persona, *, keep_containers: bool = False) -> BuildResult:
    """Scaffold, replay, and grade one persona.

    Args:
        persona: The persona to build.
        keep_containers: Leave the exercise's containers running afterwards. Useful
            when building several personas for one exercise in a row, since bring-up
            dominates the runtime.

    Returns:
        A :class:`BuildResult`. Check ``ok`` rather than catching.
    """
    result = BuildResult(persona=persona, log=[])

    def note(message: str) -> None:
        assert result.log is not None
        result.log.append(message)
        logger.info("calibrate %s: %s", persona.key, message)

    try:
        exercise = WorkspaceExercise.objects.get(slug=persona.exercise_slug)
    except WorkspaceExercise.DoesNotExist:
        result.error = (
            f"exercise {persona.exercise_slug} is not in the database; "
            "run seed_workspace_exercises first"
        )
        return result

    _close_stale_sessions(exercise)

    session = WorkspaceSession.objects.create(
        user=calibration_user(),
        exercise=exercise,
        exercise_type=exercise.exercise_type,
        difficulty=exercise.difficulty,
        time_limit_seconds=exercise.time_limit_seconds,
        hints_used=persona.hints_used,
    )
    result.session = session
    note(f"created session {session.pk}")

    try:
        scaffold_result = scaffolder.scaffold(session)
        if not scaffold_result.ok:
            raise CalibrationError(f"scaffold failed: {scaffold_result.error}")
        note(f"scaffolded {scaffold_result.workspace_path}")

        if exercise.needs_docker:
            ok, output = scaffolder.start_containers(session)
            if not ok:
                raise CalibrationError(f"containers did not come up: {output[-1500:]}")
            note("containers up")

            runner = CheckRunner(
                Path(session.workspace_path),
                compose_project=session.compose_project,
                use_container=bool(session.compose_project),
            )
            exit_code, setup_output, _ = runner.run_command(SETUP_COMMAND)
            if exit_code != 0:
                raise CalibrationError(
                    f"{SETUP_COMMAND!r} failed ({exit_code}): {setup_output[-1500:]}"
                )
            note("migrations applied")

        # The clock is backdated so the session reports the persona's elapsed time.
        # begin() takes the instant explicitly for exactly this kind of caller.
        elapsed = timedelta(seconds=int(session.time_limit_seconds * persona.fraction_time_used))
        started_at = timezone.now() - elapsed
        session.begin(now=started_at)
        note(f"clock started at T-{int(elapsed.total_seconds() // 60)}m")

        shas = apply_persona(Path(session.workspace_path), persona, started_at=started_at)
        note(f"replayed {len(shas)} commit(s)")

        session.user_notes = persona.notes_md
        session.save(update_fields=["user_notes"])

        grade = submission_service.capture_and_grade(session)
        if grade is None:
            session.refresh_from_db()
            raise CalibrationError(
                "grading did not produce a result; check the session's events for "
                "the failure (most often the model call)"
            )
        result.grade = grade
        result.ok = True
        note(f"graded {grade.letter_grade} ({grade.overall_score})")
    except Exception as exc:  # noqa: BLE001 - reported on the result, never raised
        result.error = str(exc)
        note(f"FAILED: {exc}")
        logger.exception("calibration build failed for %s", persona.key)
    finally:
        if not keep_containers and session.compose_project:
            docker_env.compose_down(session.compose_project, Path(session.workspace_path or "."))
            note("containers down")

    return result
