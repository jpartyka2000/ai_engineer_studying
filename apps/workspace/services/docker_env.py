"""Environment probing and container lifecycle for workspace exercises.

Exercises run against real Postgres and MongoDB containers, so the app has to know
whether Docker is usable *before* it scaffolds anything -- producing a workspace
the user cannot run is worse than refusing to start.

Containers are brought up during the **prepare** phase, which is deliberately
before the clock starts. After that the app only observes them; the user keeps full
``docker compose`` control, which several exercise types (CI/CD repair, latency
work) genuinely require.

These helpers intentionally duplicate ~15 lines of ``docker info`` plumbing rather
than importing from ``apps/coding/services/code_runner.py``. Those are instance
methods bound to that module's ``python-runner:latest`` image and its build path;
importing them would couple this mode to the sandbox runner's lifecycle for no
benefit.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from django.conf import settings

from apps.workspace.services import git_ops, paths

logger = logging.getLogger(__name__)

#: Below this, refuse to scaffold: a base app image plus volumes needs room.
MIN_FREE_DISK_BYTES: Final[int] = 1 * 1024**3
#: Below this, warn but allow.
LOW_FREE_DISK_BYTES: Final[int] = 5 * 1024**3

PROBE_TIMEOUT_SECONDS: Final[int] = 15


@dataclass
class DoctorReport:
    """The result of probing the local environment."""

    docker_ok: bool = False
    docker_message: str = ""
    compose_ok: bool = False
    compose_message: str = ""
    git_ok: bool = False
    git_message: str = ""
    worker_ok: bool = False
    worker_message: str = ""
    disk_free_bytes: int = 0
    workspace_root_writable: bool = False
    workspace_root: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def disk_free_gb(self) -> float:
        """Free space on the workspace volume, in GB."""
        return round(self.disk_free_bytes / 1024**3, 1)

    @property
    def disk_ok(self) -> bool:
        """Whether there is enough room to scaffold."""
        return self.disk_free_bytes >= MIN_FREE_DISK_BYTES

    @property
    def ready_without_docker(self) -> bool:
        """Whether a container-free exercise (DuckDB only) could run."""
        return self.git_ok and self.disk_ok and self.workspace_root_writable

    @property
    def ready(self) -> bool:
        """Whether a container-based exercise could run."""
        return self.ready_without_docker and self.docker_ok and self.compose_ok

    def blockers(self) -> list[str]:
        """Return the reasons an exercise cannot be started, in priority order."""
        problems: list[str] = []
        if not self.git_ok:
            problems.append(self.git_message)
        if not self.workspace_root_writable:
            problems.append(f"Workspace directory is not writable: {self.workspace_root}")
        if not self.disk_ok:
            problems.append(f"Only {self.disk_free_gb} GB free; at least 1 GB is needed")
        if not self.docker_ok:
            problems.append(self.docker_message)
        elif not self.compose_ok:
            problems.append(self.compose_message)
        return problems


def _probe(argv: list[str], timeout: int = PROBE_TIMEOUT_SECONDS) -> tuple[bool, str]:
    """Run a probe command and report success plus a human-readable message."""
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            argv, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError:
        return False, f"{argv[0]} is not installed or not on PATH"
    except subprocess.TimeoutExpired:
        return False, f"{' '.join(argv[:2])} did not respond within {timeout}s"
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        return False, detail[0] if detail else f"{argv[0]} exited {completed.returncode}"
    return True, (completed.stdout or "").strip().splitlines()[0] if completed.stdout else "ok"


def docker_available() -> tuple[bool, str]:
    """Check that the Docker daemon is running.

    Returns:
        ``(ok, message)``. The message is shown to the user verbatim, so a stopped
        Docker Desktop reads as an actionable instruction rather than a traceback.
    """
    ok, message = _probe(["docker", "info", "--format", "{{.ServerVersion}}"])
    if not ok:
        return False, f"Docker is not available: {message}. Start Docker Desktop and reload."
    return True, f"Docker {message}"


def compose_available() -> tuple[bool, str]:
    """Check that the Docker Compose v2 plugin is present."""
    ok, message = _probe(["docker", "compose", "version", "--short"])
    if not ok:
        return False, f"Docker Compose is not available: {message}"
    return True, f"Docker Compose {message}"


def worker_available(*, timeout: float = 1.5) -> tuple[bool, str]:
    """Check that the broker is reachable and a Celery worker is consuming.

    Grading re-runs a real test suite and then calls the Claude API, which takes
    60-180 seconds, so it runs as a background task rather than inside the request.
    Without a worker, submitting would appear to hang forever -- so this is surfaced
    on the prepare page rather than discovered at submit time.

    Args:
        timeout: Seconds to wait for a worker to answer a ping.

    Returns:
        ``(ok, message)``.
    """
    try:
        from config import celery_app
    except ImportError as exc:  # pragma: no cover - only if the app is misconfigured
        return False, f"Celery app is not importable: {exc}"

    try:
        connection = celery_app.connection()
        connection.ensure_connection(max_retries=0, timeout=timeout)
        connection.release()
    except Exception as exc:  # noqa: BLE001 - kombu raises a wide variety here
        return False, (
            f"Task broker is unreachable ({exc}). Start Redis with 'docker compose up -d redis'."
        )

    try:
        replies = celery_app.control.inspect(timeout=timeout).ping() or {}
    except Exception as exc:  # noqa: BLE001
        return False, f"Could not inspect workers: {exc}"

    if not replies:
        return False, (
            "The broker is up but no Celery worker is consuming. Grading runs in the "
            "background, so start one with 'celery -A config worker -l info'."
        )
    return True, f"{len(replies)} worker(s) connected"


#: Cached report plus the monotonic timestamp it was taken at.
_doctor_cache: tuple[float, DoctorReport] | None = None


def doctor(*, force: bool = False) -> DoctorReport:
    """Probe the environment, reusing a recent result.

    Probing costs two ``docker`` subprocesses, a ``git`` subprocess, a broker
    connection and a worker ping -- several seconds in total. Three different pages
    render this report, so an uncached call would make every page load crawl. The
    result is cached briefly; the "Re-check" button passes ``force``.

    Args:
        force: Skip the cache and probe again.

    Returns:
        A :class:`DoctorReport`.
    """
    global _doctor_cache  # noqa: PLW0603 - deliberate process-local cache

    ttl = getattr(settings, "WORKSPACE_DOCTOR_CACHE_SECONDS", 10)
    if not force and _doctor_cache is not None:
        taken_at, cached = _doctor_cache
        if time.monotonic() - taken_at < ttl:
            return cached

    report = _probe_environment()
    _doctor_cache = (time.monotonic(), report)
    return report


def _probe_environment() -> DoctorReport:
    """Run every environment probe. Use :func:`doctor` instead, which caches."""
    report = DoctorReport()
    report.docker_ok, report.docker_message = docker_available()
    if report.docker_ok:
        report.compose_ok, report.compose_message = compose_available()
    else:
        report.compose_message = "Not checked, because Docker is unavailable"
    report.git_ok, report.git_message = git_ops.git_available()
    report.worker_ok, report.worker_message = worker_available()
    if not report.worker_ok:
        # A missing worker blocks grading, not scaffolding, so it is a warning
        # rather than a blocker: the user can still do the exercise.
        report.warnings.append(report.worker_message)

    root = paths.workspace_root()
    report.workspace_root = str(root)
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        report.workspace_root_writable = True
    except OSError as exc:
        report.workspace_root_writable = False
        report.warnings.append(f"Cannot write to {root}: {exc}")

    try:
        report.disk_free_bytes = shutil.disk_usage(
            root if root.exists() else Path(settings.BASE_DIR)
        ).free
    except OSError:
        report.disk_free_bytes = 0

    if MIN_FREE_DISK_BYTES <= report.disk_free_bytes < LOW_FREE_DISK_BYTES:
        report.warnings.append(
            f"Only {report.disk_free_gb} GB free. Run the cleanup command if exercises "
            "start failing to build."
        )
    return report


def _compose_base(project: str, workspace: Path) -> list[str]:
    """Build the common ``docker compose`` argv for a project."""
    return ["docker", "compose", "-p", project, "--project-directory", str(workspace)]


def compose_up(project: str, workspace: Path, *, timeout: int | None = None) -> tuple[bool, str]:
    """Start an exercise's containers and wait for their healthchecks.

    Run during the prepare phase, off the clock. ``--wait`` makes Compose block
    until healthchecks pass, so the user is not handed a workspace whose database
    is still initialising.

    Args:
        project: ``COMPOSE_PROJECT_NAME`` isolating this exercise.
        workspace: The workspace directory containing ``docker-compose.yml``.
        timeout: Seconds to wait.

    Returns:
        ``(ok, combined_output)``. Output is returned on success too, because it is
        the diagnostic the user needs when a service comes up unhealthy.
    """
    limit = timeout if timeout is not None else settings.WORKSPACE_COMPOSE_UP_TIMEOUT_SECONDS
    argv = _compose_base(project, workspace) + ["up", "-d", "--wait"]
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            argv, cwd=workspace, capture_output=True, text=True, timeout=limit, check=False
        )
    except FileNotFoundError:
        return False, "docker is not installed or not on PATH"
    except subprocess.TimeoutExpired:
        return False, f"docker compose up did not finish within {limit}s"
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode == 0, output.strip()


def compose_ps(project: str, workspace: Path) -> list[dict]:
    """List an exercise's containers and their states.

    Used by the heartbeat to show a green/red pill. Purely observational: the user
    owns the container lifecycle once the clock starts.

    Args:
        project: ``COMPOSE_PROJECT_NAME``.
        workspace: The workspace directory.

    Returns:
        One dict per service with ``service``, ``state`` and ``health`` keys. Empty
        when Docker is unreachable, which the caller should treat as unknown rather
        than as "nothing running".
    """
    argv = _compose_base(project, workspace) + ["ps", "--format", "json"]
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            argv, cwd=workspace, capture_output=True, text=True, timeout=30, check=False
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []

    services: list[dict] = []
    raw = (completed.stdout or "").strip()
    if not raw:
        return []
    # Compose emits either a JSON array or newline-delimited objects depending on
    # version, so handle both rather than pinning a Compose release.
    try:
        parsed = json.loads(raw)
        entries = parsed if isinstance(parsed, list) else [parsed]
    except ValueError:
        entries = []
        for line in raw.splitlines():
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        services.append(
            {
                "service": entry.get("Service") or entry.get("Name", ""),
                "state": entry.get("State", ""),
                "health": entry.get("Health", ""),
            }
        )
    return services


def compose_down(project: str, workspace: Path, *, volumes: bool = True) -> tuple[bool, str]:
    """Stop and remove an exercise's containers.

    Best-effort by design: a dead Docker daemon must never block submission or
    teardown, so failures are reported rather than raised.

    Args:
        project: ``COMPOSE_PROJECT_NAME``.
        workspace: The workspace directory.
        volumes: Also remove named volumes, so a retry starts from clean seed data.

    Returns:
        ``(ok, output)``.
    """
    argv = _compose_base(project, workspace) + ["down", "--remove-orphans"]
    if volumes:
        argv.append("--volumes")
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            argv,
            cwd=workspace if workspace.is_dir() else None,
            capture_output=True,
            text=True,
            timeout=settings.WORKSPACE_COMPOSE_DOWN_TIMEOUT_SECONDS,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("compose down failed for project %s: %s", project, exc)
        return False, str(exc)
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode == 0, output.strip()
