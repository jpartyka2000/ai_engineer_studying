"""Teardown and cleanup for workspace sessions.

Three jobs:

* :func:`teardown` -- stop an exercise's containers and move its directory into the
  archive. Directories are **moved, never deleted**, so a mid-exercise mistake can
  still be recovered.
* :func:`reap_stale_sessions` -- the answer to "the user never submitted". The
  deadline lives in the database, so it is honoured whether or not a browser ever
  comes back.
* :func:`prune_archive` -- the only place archived work is actually removed, and
  it is off unless explicitly enabled.
"""

from __future__ import annotations

import logging
import shutil
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.workspace.exceptions import NotDeletableError, UnsafePathError
from apps.workspace.models import WorkspaceEvent, WorkspaceSession
from apps.workspace.services import docker_env, paths

logger = logging.getLogger(__name__)


def active_session_ids() -> set[int]:
    """Return the ids of sessions that still own their workspace directory.

    Passed to the path kernel so it refuses to delete a live session's work even if
    a caller asks it to.
    """
    return set(
        WorkspaceSession.objects.filter(status__in=WorkspaceSession.ACTIVE_STATUSES).values_list(
            "pk", flat=True
        )
    )


def archive_workspace(session: WorkspaceSession) -> Path | None:
    """Move a session's workspace into the archive.

    Moving rather than deleting is deliberate: a user who abandons an exercise by
    accident has not lost their work, and the archive is pruned separately and
    explicitly.

    Args:
        session: The session whose directory should be archived.

    Returns:
        The archive destination, or ``None`` if there was nothing to move.
    """
    if not session.workspace_path:
        return None
    source = Path(session.workspace_path)
    if not source.is_dir():
        return None

    try:
        paths.assert_safe_workspace_path(source)
    except UnsafePathError:
        logger.exception("refusing to archive unsafe path %s", source)
        return None

    destination_root = paths.archive_root()
    destination_root.mkdir(parents=True, exist_ok=True)
    stamp = timezone.now().strftime("%Y%m%d%H%M%S")
    destination = destination_root / f"{source.name}--s{session.pk}--{stamp}"

    try:
        shutil.move(str(source), str(destination))
    except OSError as exc:
        logger.warning("could not archive %s: %s", source, exc)
        return None
    return destination


def remove_origin(session: WorkspaceSession) -> bool:
    """Delete the bare repository that emulated GitHub for a session.

    Args:
        session: The session whose origin should be removed.

    Returns:
        Whether anything was removed.
    """
    if not session.origin_path:
        return False
    origin = Path(session.origin_path)
    if not origin.is_dir():
        return False
    try:
        paths.assert_safe_workspace_path(origin)
    except UnsafePathError:
        logger.exception("refusing to remove unsafe origin path %s", origin)
        return False
    # The bare repo carries no sentinel (it is not a workspace), so it is removed
    # directly after the containment check rather than through destroy().
    try:
        shutil.rmtree(origin)
    except OSError as exc:
        logger.warning("could not remove origin %s: %s", origin, exc)
        return False
    return True


def teardown(
    session: WorkspaceSession,
    *,
    reason: str | None = None,
    stop_containers: bool = True,
) -> dict[str, bool]:
    """Stop an exercise's containers and archive its workspace.

    Every step is best-effort and independently reported. A dead Docker daemon must
    not prevent the directory from being archived, and a failed archive must not
    prevent the session from being closed.

    Args:
        session: The session to tear down.
        reason: An :class:`~apps.workspace.models.WorkspaceSession.EndReason`. When
            given, the session is also ended.
        stop_containers: Whether to run ``docker compose down``.

    Returns:
        A dict reporting what succeeded: ``containers``, ``archived``, ``origin``.
    """
    outcome = {"containers": False, "archived": False, "origin": False}
    workspace = Path(session.workspace_path) if session.workspace_path else None

    if stop_containers and session.compose_project and workspace:
        ok, output = docker_env.compose_down(session.compose_project, workspace)
        outcome["containers"] = ok
        if not ok:
            logger.info("containers for session %s not cleanly stopped: %s", session.pk, output)

    # End the session before archiving so the path kernel no longer sees it as
    # active and will permit the move.
    if reason is not None and session.is_active:
        session.end_session(reason)

    outcome["archived"] = archive_workspace(session) is not None
    outcome["origin"] = remove_origin(session)

    WorkspaceEvent.log(session, WorkspaceEvent.Kind.TORN_DOWN, **outcome)
    return outcome


def reap_stale_sessions(*, now=None) -> dict[str, list[int]]:
    """Close out sessions that the user never finished.

    Two categories:

    * **Past the deadline and still in progress.** Captured from disk, marked timed
      out with ``end_reason="reaped"``, and queued for grading. The buzzer is not an
      automatic F, so this genuinely grades whatever partial work exists.
    * **Stuck before the clock started.** A scaffolded-but-never-begun session is
      abandoned after ``WORKSPACE_STALE_PREPARE_HOURS`` so its directory and
      containers do not accumulate.

    Args:
        now: Override for the current time, for testing.

    Returns:
        A dict with ``reaped`` and ``abandoned`` lists of session ids.
    """
    moment = now or timezone.now()
    grace = timedelta(seconds=settings.WORKSPACE_SUBMIT_GRACE_SECONDS)
    result: dict[str, list[int]] = {"reaped": [], "abandoned": []}

    overdue = WorkspaceSession.objects.filter(
        status=WorkspaceSession.Status.IN_PROGRESS,
        expires_at__lt=moment - grace,
    )
    for session in overdue:
        # Imported here: submission capture pulls in the grading pipeline, and the
        # reaper is also imported by admin.py, which would otherwise create a cycle.
        from apps.workspace.services import submission as submission_service

        try:
            submission_service.capture_and_grade(
                session, end_reason=WorkspaceSession.EndReason.REAPED
            )
            result["reaped"].append(session.pk)
            WorkspaceEvent.log(session, WorkspaceEvent.Kind.REAPED)
        except Exception:  # noqa: BLE001 - one bad session must not stop the sweep
            logger.exception("could not reap session %s", session.pk)

    cutoff = moment - timedelta(hours=settings.WORKSPACE_STALE_PREPARE_HOURS)
    stalled = WorkspaceSession.objects.filter(
        status__in=[WorkspaceSession.Status.SCAFFOLDING, WorkspaceSession.Status.READY],
        created_at__lt=cutoff,
    )
    for session in stalled:
        try:
            teardown(session, reason=WorkspaceSession.EndReason.ABANDONED)
            result["abandoned"].append(session.pk)
        except Exception:  # noqa: BLE001 - keep sweeping
            logger.exception("could not abandon stalled session %s", session.pk)

    return result


def prune_archive(
    *, older_than_days: int | None = None, dry_run: bool = True
) -> list[tuple[Path, str]]:
    """Delete archived workspaces older than a retention window.

    The only code path in the project that removes a user's archived work, so it is
    guarded three ways: it is dry-run by default, it refuses unless
    ``WORKSPACE_ALLOW_DESTRUCTIVE_CLEANUP`` is enabled, and every deletion still
    goes through the sentinel-gated path kernel.

    Args:
        older_than_days: Retention window; defaults to
            ``WORKSPACE_ARCHIVE_RETENTION_DAYS``.
        dry_run: When true, report what would be removed without touching anything.

    Returns:
        A list of ``(path, outcome)`` pairs where outcome is ``"would-delete"``,
        ``"deleted"``, ``"kept"``, or a refusal reason.
    """
    days = (
        older_than_days
        if older_than_days is not None
        else settings.WORKSPACE_ARCHIVE_RETENTION_DAYS
    )
    cutoff = timezone.now() - timedelta(days=days)
    archive = paths.archive_root()
    if not archive.is_dir():
        return []

    live = active_session_ids()
    report: list[tuple[Path, str]] = []

    for candidate in sorted(archive.iterdir()):
        if not candidate.is_dir():
            continue
        modified = timezone.datetime.fromtimestamp(
            candidate.stat().st_mtime, tz=timezone.get_current_timezone()
        )
        if modified >= cutoff:
            report.append((candidate, "kept"))
            continue

        if dry_run:
            report.append((candidate, "would-delete"))
            continue

        if not settings.WORKSPACE_ALLOW_DESTRUCTIVE_CLEANUP:
            report.append((candidate, "refused: WORKSPACE_ALLOW_DESTRUCTIVE_CLEANUP is off"))
            continue

        try:
            paths.destroy(candidate, active_session_ids=live)
            report.append((candidate, "deleted"))
        except (NotDeletableError, UnsafePathError) as exc:
            report.append((candidate, f"refused: {exc}"))
    return report
