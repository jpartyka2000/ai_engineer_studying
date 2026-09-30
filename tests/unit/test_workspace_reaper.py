"""Tests for workspace teardown and cleanup.

``prune_archive`` is the only code in the project that removes a user's archived
work. It is guarded three ways -- dry-run by default, an explicit settings flag,
and the sentinel-gated path kernel -- and each guard is tested independently here,
because any one of them failing alone is enough to lose work.
"""

import os
import time
from pathlib import Path

import pytest
from django.utils import timezone
from freezegun import freeze_time

from apps.workspace.enums import BaseApp, Difficulty, ExerciseType
from apps.workspace.models import WorkspaceEvent, WorkspaceExercise, WorkspaceSession
from apps.workspace.services import paths, reaper

pytestmark = pytest.mark.django_db


@pytest.fixture
def ws_root(tmp_path, settings):
    root = tmp_path / "home" / "user" / "workspaces"
    root.mkdir(parents=True)
    settings.WORKSPACE_ROOT = root
    return root.resolve()


@pytest.fixture
def exercise(db):
    return WorkspaceExercise.objects.create(
        exercise_number=1,
        slug="ex-001-demo",
        title="Demo",
        exercise_type=ExerciseType.CRITICAL_BUG,
        base_app=BaseApp.TENANTSAAS,
        difficulty=Difficulty.BEGINNER,
        defect_class="silent_except",
        brief_md="brief",
        definition_of_done=["R1: passes"],
        time_limit_seconds=20 * 60,
        expected_time_minutes=14,
        protected_paths=["tests/**"],
    )


def make_session(user, exercise, ws_root, *, status=WorkspaceSession.Status.READY, name=None):
    """Create a session with a real scaffolded-looking directory on disk."""
    session = WorkspaceSession.objects.create(
        user=user,
        exercise=exercise,
        exercise_type=exercise.exercise_type,
        difficulty=exercise.difficulty,
        time_limit_seconds=exercise.time_limit_seconds,
        status=status,
    )
    directory = ws_root / (name or f"ex-001-demo-s{session.pk}")
    directory.mkdir()
    (directory / "app.py").write_text("x = 1\n")
    paths.write_sentinel(directory, session_id=session.pk, exercise_slug=exercise.slug)
    session.workspace_path = str(directory)
    session.sentinel_written = True
    session.save(update_fields=["workspace_path", "sentinel_written"])
    return session


# ---------------------------------------------------------------------------
# Archiving moves rather than deletes
# ---------------------------------------------------------------------------


def test_archive_moves_the_directory_and_keeps_the_contents(user, exercise, ws_root):
    session = make_session(user, exercise, ws_root)
    original = Path(session.workspace_path)

    destination = reaper.archive_workspace(session)

    assert destination is not None
    assert not original.exists()
    assert (destination / "app.py").read_text() == "x = 1\n"
    assert destination.parent == paths.archive_root()


def test_archive_name_records_the_session(user, exercise, ws_root):
    session = make_session(user, exercise, ws_root)
    destination = reaper.archive_workspace(session)
    assert f"--s{session.pk}--" in destination.name


def test_archive_returns_none_when_there_is_nothing_to_move(user, exercise, ws_root):
    session = make_session(user, exercise, ws_root)
    Path(session.workspace_path).rename(ws_root / "moved-away")
    assert reaper.archive_workspace(session) is None


def test_archive_refuses_a_path_outside_the_workspace_root(user, exercise, ws_root, tmp_path):
    session = make_session(user, exercise, ws_root)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "precious.txt").write_text("keep me")
    session.workspace_path = str(outside)
    session.save(update_fields=["workspace_path"])

    assert reaper.archive_workspace(session) is None
    assert (outside / "precious.txt").exists()


# ---------------------------------------------------------------------------
# Origin removal
# ---------------------------------------------------------------------------


def test_remove_origin_deletes_the_bare_repo(user, exercise, ws_root):
    session = make_session(user, exercise, ws_root)
    origin = paths.origins_root() / "ex-001-demo.git"
    origin.mkdir(parents=True)
    (origin / "HEAD").write_text("ref: refs/heads/main\n")
    session.origin_path = str(origin)
    session.save(update_fields=["origin_path"])

    assert reaper.remove_origin(session) is True
    assert not origin.exists()


def test_remove_origin_refuses_a_path_outside_the_root(user, exercise, ws_root, tmp_path):
    session = make_session(user, exercise, ws_root)
    outside = tmp_path / "not-ours.git"
    outside.mkdir()
    session.origin_path = str(outside)
    session.save(update_fields=["origin_path"])

    assert reaper.remove_origin(session) is False
    assert outside.exists()


def test_remove_origin_is_a_noop_without_an_origin(user, exercise, ws_root):
    session = make_session(user, exercise, ws_root)
    assert reaper.remove_origin(session) is False


# ---------------------------------------------------------------------------
# teardown
# ---------------------------------------------------------------------------


def test_teardown_ends_the_session_and_archives(user, exercise, ws_root):
    session = make_session(user, exercise, ws_root)
    original = Path(session.workspace_path)

    outcome = reaper.teardown(
        session, reason=WorkspaceSession.EndReason.ABANDONED, stop_containers=False
    )

    session.refresh_from_db()
    assert session.status == WorkspaceSession.Status.ABANDONED
    assert outcome["archived"] is True
    assert not original.exists()


def test_teardown_logs_an_event(user, exercise, ws_root):
    session = make_session(user, exercise, ws_root)
    reaper.teardown(session, reason=WorkspaceSession.EndReason.ABANDONED, stop_containers=False)
    assert session.events.filter(kind=WorkspaceEvent.Kind.TORN_DOWN).exists()


def test_teardown_ends_the_session_before_archiving(user, exercise, ws_root):
    """The path kernel refuses to touch a live session's directory.

    If teardown archived first and ended second, an in-progress session could never
    be torn down at all.
    """
    session = make_session(user, exercise, ws_root, status=WorkspaceSession.Status.IN_PROGRESS)
    session.begin()

    outcome = reaper.teardown(
        session, reason=WorkspaceSession.EndReason.ABANDONED, stop_containers=False
    )
    assert outcome["archived"] is True


def test_teardown_without_a_reason_leaves_the_status_alone(user, exercise, ws_root):
    session = make_session(user, exercise, ws_root)
    reaper.teardown(session, stop_containers=False)
    session.refresh_from_db()
    assert session.status == WorkspaceSession.Status.READY


# ---------------------------------------------------------------------------
# active_session_ids
# ---------------------------------------------------------------------------


def test_active_session_ids_includes_live_sessions_only(user, exercise, ws_root):
    live = make_session(user, exercise, ws_root, status=WorkspaceSession.Status.IN_PROGRESS)
    assert reaper.active_session_ids() == {live.pk}

    live.end_session(WorkspaceSession.EndReason.SUBMITTED)
    assert reaper.active_session_ids() == set()


# ---------------------------------------------------------------------------
# Reaping stale prepare-phase sessions
# ---------------------------------------------------------------------------


def test_a_session_stuck_before_the_clock_is_abandoned(user, exercise, ws_root, settings):
    settings.WORKSPACE_STALE_PREPARE_HOURS = 2
    with freeze_time("2026-03-01 10:00:00"):
        session = make_session(user, exercise, ws_root, status=WorkspaceSession.Status.READY)

    with freeze_time("2026-03-01 13:00:00"):
        result = reaper.reap_stale_sessions()

    session.refresh_from_db()
    assert session.pk in result["abandoned"]
    assert session.status == WorkspaceSession.Status.ABANDONED


def test_a_recent_prepare_session_is_left_alone(user, exercise, ws_root, settings):
    settings.WORKSPACE_STALE_PREPARE_HOURS = 2
    with freeze_time("2026-03-01 10:00:00"):
        session = make_session(user, exercise, ws_root, status=WorkspaceSession.Status.READY)

    with freeze_time("2026-03-01 10:30:00"):
        result = reaper.reap_stale_sessions()

    session.refresh_from_db()
    assert result["abandoned"] == []
    assert session.status == WorkspaceSession.Status.READY


def test_a_session_inside_its_deadline_is_not_reaped(user, exercise, ws_root):
    with freeze_time("2026-03-01 10:00:00"):
        session = make_session(user, exercise, ws_root, status=WorkspaceSession.Status.IN_PROGRESS)
        session.begin()

    with freeze_time("2026-03-01 10:10:00"):
        result = reaper.reap_stale_sessions()

    session.refresh_from_db()
    assert result["reaped"] == []
    assert session.status == WorkspaceSession.Status.IN_PROGRESS


# ---------------------------------------------------------------------------
# prune_archive: the destructive path
# ---------------------------------------------------------------------------


def age(directory: Path, days: int) -> None:
    """Backdate a directory's mtime so it looks older than the retention window."""
    old = time.time() - days * 86_400
    os.utime(directory, (old, old))


@pytest.fixture
def archived(user, exercise, ws_root):
    """An archived workspace, 30 days old, carrying a valid sentinel."""
    session = make_session(user, exercise, ws_root)
    session.end_session(WorkspaceSession.EndReason.SUBMITTED)
    destination = reaper.archive_workspace(session)
    age(destination, days=30)
    return destination


def test_prune_is_dry_run_by_default(archived, settings):
    """The default invocation must never delete anything."""
    settings.WORKSPACE_ALLOW_DESTRUCTIVE_CLEANUP = True

    report = reaper.prune_archive(older_than_days=7)

    assert (archived, "would-delete") in report
    assert archived.exists()


def test_prune_refuses_without_the_destructive_flag(archived, settings):
    """Second guard: even an explicit non-dry-run needs the settings flag."""
    settings.WORKSPACE_ALLOW_DESTRUCTIVE_CLEANUP = False

    report = reaper.prune_archive(older_than_days=7, dry_run=False)

    outcome = dict(report)[archived]
    assert "refused" in outcome
    assert "WORKSPACE_ALLOW_DESTRUCTIVE_CLEANUP" in outcome
    assert archived.exists()


def test_prune_deletes_when_both_guards_are_satisfied(archived, settings):
    settings.WORKSPACE_ALLOW_DESTRUCTIVE_CLEANUP = True

    report = reaper.prune_archive(older_than_days=7, dry_run=False)

    assert dict(report)[archived] == "deleted"
    assert not archived.exists()


def test_prune_keeps_recent_archives(user, exercise, ws_root, settings):
    settings.WORKSPACE_ALLOW_DESTRUCTIVE_CLEANUP = True
    session = make_session(user, exercise, ws_root)
    session.end_session(WorkspaceSession.EndReason.SUBMITTED)
    recent = reaper.archive_workspace(session)

    report = reaper.prune_archive(older_than_days=7, dry_run=False)

    assert dict(report)[recent] == "kept"
    assert recent.exists()


def test_prune_refuses_a_directory_without_a_sentinel(ws_root, settings):
    """Third guard: the path kernel still applies inside the archive.

    Something the user dropped into the archive directory by hand is not ours to
    delete, however old it is.
    """
    settings.WORKSPACE_ALLOW_DESTRUCTIVE_CLEANUP = True
    archive = paths.archive_root()
    archive.mkdir(parents=True, exist_ok=True)
    intruder = archive / "my-own-backup"
    intruder.mkdir()
    (intruder / "thesis.txt").write_text("years of work")
    age(intruder, days=365)

    report = reaper.prune_archive(older_than_days=7, dry_run=False)

    assert "refused" in dict(report)[intruder]
    assert (intruder / "thesis.txt").read_text() == "years of work"


def test_prune_handles_a_missing_archive_directory(ws_root):
    assert reaper.prune_archive(older_than_days=7) == []


def test_prune_uses_the_configured_retention_by_default(archived, settings):
    settings.WORKSPACE_ALLOW_DESTRUCTIVE_CLEANUP = True
    settings.WORKSPACE_ARCHIVE_RETENTION_DAYS = 90

    report = reaper.prune_archive(dry_run=False)

    # 30 days old, 90-day retention: must survive.
    assert dict(report)[archived] == "kept"
    assert archived.exists()


def test_prune_ignores_loose_files_in_the_archive(ws_root, settings):
    settings.WORKSPACE_ALLOW_DESTRUCTIVE_CLEANUP = True
    archive = paths.archive_root()
    archive.mkdir(parents=True, exist_ok=True)
    stray = archive / "README.txt"
    stray.write_text("notes")

    report = reaper.prune_archive(older_than_days=0, dry_run=False)

    assert stray not in dict(report)
    assert stray.exists()


def test_timezone_aware_comparison_does_not_crash(archived, settings):
    """Regression guard: naive/aware datetime mixing raises TypeError."""
    settings.WORKSPACE_ALLOW_DESTRUCTIVE_CLEANUP = True
    assert timezone.is_aware(timezone.now())
    reaper.prune_archive(older_than_days=7, dry_run=True)
