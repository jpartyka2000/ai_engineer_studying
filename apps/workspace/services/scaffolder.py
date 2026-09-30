"""Materialize an exercise template into a real repository on disk.

The user works in their own terminal, editor and browser against the directory this
produces, so it has to look and behave like a repository they inherited: plausible
multi-author history, a clean working tree, a real ``origin`` they can push to, and
services already running.

Ordering here is load-bearing:

* **The defect is applied before the history is created.** The user's work is diffed
  against the seed commit, so if the mutation were committed afterwards the diff
  would show the defect being *introduced* — and `git log` would hand over the
  answer. Applying it first makes the defect simply "how the code is".
* **`.env` is written after the history.** It holds allocated host ports, must never
  be committed, and writing it last guarantees the working tree is clean at T=0. A
  dirty tree at the starting line would corrupt every diff taken later.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.workspace.exceptions import (
    GitCommandError,
    ManifestError,
    PortAllocationError,
    ScaffoldError,
    UnsafePathError,
)
from apps.workspace.models import WorkspaceEvent, WorkspaceSession
from apps.workspace.schemas import Manifest
from apps.workspace.services import check_runner, docker_env, git_ops, manifest, paths, ports
from apps.workspace.services.paths import assert_safe_workspace_path

logger = logging.getLogger(__name__)

#: Never copied out of a template into a workspace.
COPY_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "*.pyo", ".DS_Store", ".pytest_cache", ".ruff_cache", ".git"
)

#: Directory inside the template holding reference material for the grader. Its
#: presence in a workspace would give away the answer, so it is never copied.
SOLUTION_DIRNAME = "solution"


@dataclass
class ScaffoldResult:
    """Outcome of materializing a workspace."""

    ok: bool = False
    workspace_path: str = ""
    seed_commit_sha: str = ""
    origin_path: str = ""
    compose_project: str = ""
    host_ports: dict[str, int] = field(default_factory=dict)
    protected_hashes: dict[str, str] = field(default_factory=dict)
    template_checksum: str = ""
    log: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def log_text(self) -> str:
        """The scaffolding log as a single string, for display on failure."""
        return "\n".join(self.log)


def _parse_author(author: str) -> tuple[str, str]:
    """Split a ``"Name <email>"`` string into its parts.

    Args:
        author: An author string from the manifest.

    Returns:
        ``(name, email)``, falling back to a generic identity if unparseable.
    """
    if "<" in author and author.rstrip().endswith(">"):
        name, _, rest = author.partition("<")
        return name.strip(), rest.rstrip(">").strip()
    return author.strip() or "Dev Team", "dev@example.com"


def _commit_env(author: str, date: str) -> dict[str, str]:
    """Build the git environment that backdates and attributes a seed commit."""
    name, email = _parse_author(author)
    return {
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_NAME": name,
        "GIT_COMMITTER_EMAIL": email,
        "GIT_COMMITTER_DATE": date,
    }


def compose_project_name(session: WorkspaceSession) -> str:
    """Build a Compose project name unique to this session.

    Prefixed so it cannot collide with the study app's own ``ai_interview_prep_db``
    and ``_redis`` containers.
    """
    return f"aiprep-ex{session.exercise.exercise_number:03d}-s{session.pk}"


class WorkspaceScaffolder:
    """Creates workspaces on disk for :class:`WorkspaceSession` rows."""

    def __init__(self, session: WorkspaceSession) -> None:
        self.session = session
        self.exercise = session.exercise
        self.result = ScaffoldResult()

    # -- logging ----------------------------------------------------------

    def _log(self, message: str) -> None:
        """Record a scaffolding step, both for the user and the server log."""
        self.result.log.append(message)
        logger.info("scaffold s%s: %s", self.session.pk, message)

    # -- steps ------------------------------------------------------------

    def _preflight(self) -> None:
        """Refuse to scaffold into an environment that cannot run the exercise.

        Producing a workspace the user cannot start is worse than refusing: they
        would discover it only after the clock was theirs to start.
        """
        report = docker_env.doctor()
        if not report.git_ok:
            raise ScaffoldError(report.git_message)
        if not report.workspace_root_writable:
            raise ScaffoldError(f"Workspace directory is not writable: {report.workspace_root}")
        if not report.disk_ok:
            raise ScaffoldError(f"Only {report.disk_free_gb} GB free; at least 1 GB is needed")
        if self.exercise.needs_docker and not (report.docker_ok and report.compose_ok):
            raise ScaffoldError(report.docker_message or report.compose_message)
        self._log("Environment check passed.")

    def _target_directory(self) -> Path:
        """Resolve, and if necessary clear, the destination directory.

        Collision policy: a directory carrying our sentinel from a finished session
        is archived; one with no sentinel is left strictly alone, because it is not
        ours and may hold the user's own work.
        """
        name = paths.session_dir_name(self.exercise.exercise_number, self.exercise.slug)
        target = assert_safe_workspace_path(paths.workspace_root() / name)

        if target.exists():
            sentinel = paths.read_sentinel(target)
            if sentinel is None:
                raise ScaffoldError(
                    f"{target} already exists and was not created by this app, so it "
                    "will not be touched. Move or rename it and try again."
                )
            stamp = timezone.now().strftime("%Y%m%d%H%M%S")
            archive = (
                paths.archive_root() / f"{target.name}--s{sentinel.get('session_id')}--{stamp}"
            )
            archive.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(archive))
            self._log(f"Archived a previous attempt to {archive.name}.")

        target.mkdir(parents=True)
        return target

    def _copy_template(self, target: Path, template_name: str) -> None:
        """Copy the pristine tree, plus any DB seed scripts, into the workspace."""
        repo = manifest.repo_dir(template_name)
        shutil.copytree(repo, target, dirs_exist_ok=True, ignore=COPY_IGNORE)
        self._log(f"Copied template {template_name} into the workspace.")

        seed = manifest.template_dir(template_name) / manifest.SEED_DIRNAME
        if seed.is_dir():
            shutil.copytree(
                seed, target / manifest.SEED_DIRNAME, dirs_exist_ok=True, ignore=COPY_IGNORE
            )
            self._log("Copied database seed scripts.")

        # Belt and braces: the grader's reference notes must never reach a workspace.
        leaked = target / SOLUTION_DIRNAME
        if leaked.exists():
            shutil.rmtree(leaked)
            self._log("Removed solution material that must not ship to a workspace.")

    def _apply_mutations(self, target: Path) -> None:
        """Inject the exercise's defect, before any history exists.

        Done first so the defect is indistinguishable from ordinary code: were it
        committed after the seed history, the diff taken at submit time would show
        the defect being introduced and ``git log`` would give the answer away.
        """
        mutations = self.exercise.mutations or []
        if not mutations:
            self._log("No mutations to apply (build-shaped exercise).")
            return

        patch_root = paths.template_root() / manifest.PATCHES_DIRNAME / self.exercise.slug
        for step in mutations:
            operation = step.get("op")
            if operation != "apply_patch":
                raise ScaffoldError(f"Unsupported mutation op {operation!r}")
            patch_file = patch_root / step["patch"]
            if not patch_file.is_file():
                raise ScaffoldError(f"Mutation patch not found: {patch_file}")
            git_ops.run_git(target, "apply", "--whitespace=nowarn", str(patch_file))
            self._log(f"Applied mutation {patch_file.name}.")

    def _exclude_harness_artifacts(self, target: Path) -> None:
        """Hide this app's own files from git, using local-only excludes.

        The deletion-guard sentinel and the harness scratch directory live inside the
        workspace but are not part of the exercise. They go in ``.git/info/exclude``
        rather than the committed ``.gitignore`` for two reasons: the exercise's
        ``.gitignore`` is code the user reads and should not be littered with harness
        detail, and ``info/exclude`` is never committed, so it cannot show up in a
        diff either.
        """
        exclude_file = target / ".git" / "info" / "exclude"
        exclude_file.parent.mkdir(parents=True, exist_ok=True)
        existing = exclude_file.read_text(encoding="utf-8") if exclude_file.exists() else ""
        entries = [
            settings.WORKSPACE_SENTINEL_FILENAME,
            f"{check_runner.GRADING_DIR}/",
        ]
        additions = [entry for entry in entries if entry not in existing]
        if additions:
            with exclude_file.open("a", encoding="utf-8") as handle:
                handle.write("\n# AI Interview Prep harness files; not part of the exercise.\n")
                for entry in additions:
                    handle.write(f"{entry}\n")

    def _create_history(self, target: Path, spec: Manifest) -> str:
        """Create plausible multi-author git history from the manifest.

        Backdated and attributed, because ``git log`` and ``git bisect`` being
        genuinely useful is a large part of what makes this feel like inherited code
        rather than a puzzle.

        Returns:
            The SHA of the final seed commit.
        """
        git_ops.run_git(target, "init", "-q")
        git_ops.run_git(target, "symbolic-ref", "HEAD", "refs/heads/main")
        self._exclude_harness_artifacts(target)

        for index, commit in enumerate(spec.seed_commits):
            git_ops.run_git(target, "add", "--", *commit.paths)
            git_ops.run_git(
                target,
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                commit.message,
                env_extra=_commit_env(commit.author, commit.date),
            )
            self._log(
                f"Seed commit {index + 1}/{len(spec.seed_commits)}: {commit.message.splitlines()[0]}"
            )

        for branch in spec.seed_branches:
            sha = git_ops.run_git(
                target, "rev-parse", f"HEAD~{len(spec.seed_commits) - 1 - branch.from_commit_index}"
            )
            git_ops.run_git(target, "branch", branch.name, sha)
            self._log(f"Created seed branch {branch.name}.")

        head = git_ops.head_sha(target)
        # Tagged so a rebase cannot make the diff base unreachable.
        git_ops.run_git(target, "tag", "-f", "_seed", head)
        return head

    def _create_origin(self, target: Path, spec: Manifest) -> str:
        """Create a bare repository so push, pull and fetch all work offline.

        This is what makes "all basic git operations" true rather than
        approximately true, with no network and no credentials involved.
        """
        origins = paths.origins_root()
        origins.mkdir(parents=True, exist_ok=True)
        origin = assert_safe_workspace_path(
            origins / f"{self.exercise.slug}-s{self.session.pk}.git"
        )
        if origin.exists():
            shutil.rmtree(origin)

        git_ops.run_git(origins, "init", "--bare", "-q", origin.name)
        git_ops.run_git(origin, "symbolic-ref", "HEAD", "refs/heads/main")
        git_ops.run_git(target, "remote", "add", "origin", str(origin))
        git_ops.run_git(target, "push", "-q", "-u", "origin", "main")
        for branch in spec.seed_branches:
            git_ops.run_git(target, "push", "-q", "origin", branch.name)
        self._log("Created a local 'origin' remote; push, pull and fetch all work.")
        return str(origin)

    def _render_env(self, target: Path, spec: Manifest, host_ports: dict[str, int]) -> None:
        """Write ``.env`` with the allocated ports.

        Written after the history and mode 0600. It is gitignored, so the working
        tree stays clean at T=0.
        """
        lines = [
            "# Generated by AI Interview Prep at scaffold time. Not committed.",
            f"COMPOSE_PROJECT_NAME={self.result.compose_project}",
            "",
            "# Host ports allocated to avoid colliding with anything already running.",
        ]
        for service, port in sorted(host_ports.items()):
            lines.append(f"{ports.env_var_for(service)}={port}")

        lines.append("")
        for key, value in spec.env.extra.items():
            lines.append(f"{key}={value}")

        # Container-to-container, so the in-network port, not the published one.
        database = spec.env.extra.get("POSTGRES_DB", "app")
        user = spec.env.extra.get("POSTGRES_USER", "postgres")
        password = spec.env.extra.get("POSTGRES_PASSWORD", "postgres")
        if "postgres" in spec.ports:
            lines.append(f"DATABASE_URL=postgresql://{user}:{password}@db:5432/{database}")
        if "mongodb" in spec.ports:
            lines.append("MONGO_URL=mongodb://mongo:27017/app")

        if spec.env.requires_anthropic_key:
            key = getattr(settings, "ANTHROPIC_API_KEY", "")
            if not key:
                raise ScaffoldError(
                    "This exercise needs ANTHROPIC_API_KEY set, because its chatbot "
                    "cannot run without it."
                )
            lines.append(f"ANTHROPIC_API_KEY={key}")

        destination = target / ".env"
        destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
        destination.chmod(0o600)
        self._log("Wrote .env with the allocated ports.")

    def _assert_clean_tree(self, target: Path) -> None:
        """Assert the working tree is clean before handing it over.

        A dirty tree at the starting line would make every later diff include
        changes the user never made.
        """
        status = git_ops.run_git(target, "status", "--porcelain")
        if status:
            raise ScaffoldError(
                "Scaffolded workspace is not clean, which would corrupt the diff "
                f"taken at submit time:\n{status}"
            )
        self._log("Working tree is clean.")

    # -- orchestration ----------------------------------------------------

    def create(self) -> ScaffoldResult:
        """Materialize the workspace.

        Rolls back the directory on failure, so a half-built workspace is never left
        behind for the user to trip over.

        Returns:
            A :class:`ScaffoldResult`. Check ``ok`` rather than catching.
        """
        WorkspaceEvent.log(self.session, WorkspaceEvent.Kind.SCAFFOLD_STARTED)
        target: Path | None = None
        try:
            self._preflight()
            template_name = self.exercise.template_dir or self.exercise.base_app
            spec = manifest.load_manifest(template_name)

            target = self._target_directory()
            self.result.workspace_path = str(target)
            paths.write_sentinel(
                target, session_id=self.session.pk, exercise_slug=self.exercise.slug
            )

            self._copy_template(target, template_name)

            self.result.compose_project = compose_project_name(self.session)
            self.result.host_ports = ports.allocate(sorted(spec.ports))
            if self.result.host_ports:
                self._log(
                    "Allocated host ports: "
                    + ", ".join(f"{k}={v}" for k, v in sorted(self.result.host_ports.items()))
                )

            self._apply_mutations(target)
            self.result.seed_commit_sha = self._create_history(target, spec)
            self.result.origin_path = self._create_origin(target, spec)
            self._render_env(target, spec, self.result.host_ports)
            self._assert_clean_tree(target)

            self.result.protected_hashes = check_runner.record_protected_hashes(
                target, self.exercise.protected_paths or []
            )
            self._log(f"Recorded {len(self.result.protected_hashes)} protected file hashes.")

            self.result.ok = True
            WorkspaceEvent.log(self.session, WorkspaceEvent.Kind.SCAFFOLD_OK)
        except (
            ScaffoldError,
            ManifestError,
            GitCommandError,
            PortAllocationError,
            UnsafePathError,
            OSError,
        ) as exc:
            self.result.ok = False
            self.result.error = str(exc)
            self._log(f"FAILED: {exc}")
            logger.exception("scaffold failed for session %s", self.session.pk)
            if target is not None and target.is_dir():
                try:
                    # The sentinel is present, so deletion is permitted.
                    paths.destroy(target)
                    self._log("Rolled back the partial workspace.")
                except Exception:  # noqa: BLE001 - never mask the original failure
                    logger.exception("could not roll back %s", target)
            WorkspaceEvent.log(
                self.session, WorkspaceEvent.Kind.SCAFFOLD_FAILED, error=self.result.error
            )

        return self.result


def scaffold(session: WorkspaceSession) -> ScaffoldResult:
    """Materialize a session's workspace and persist the outcome.

    Args:
        session: The session to scaffold. Must be in ``SCAFFOLDING`` status.

    Returns:
        The :class:`ScaffoldResult`.
    """
    result = WorkspaceScaffolder(session).create()

    session.workspace_path = result.workspace_path
    session.sentinel_written = bool(result.workspace_path) and result.ok
    session.seed_commit_sha = result.seed_commit_sha
    session.origin_path = result.origin_path
    session.compose_project = result.compose_project
    session.host_ports = result.host_ports
    session.scaffold_log = result.log_text
    session.status = WorkspaceSession.Status.READY if result.ok else WorkspaceSession.Status.FAILED
    if not result.ok:
        session.end_reason = WorkspaceSession.EndReason.FAILED
    session.save(
        update_fields=[
            "workspace_path",
            "sentinel_written",
            "seed_commit_sha",
            "origin_path",
            "compose_project",
            "host_ports",
            "scaffold_log",
            "status",
            "end_reason",
        ]
    )

    # Protected-file hashes are recorded against the exercise's check spec, so the
    # tampering check has something to compare against at submit time.
    if result.ok and result.protected_hashes:
        spec = dict(session.exercise.grading_spec or {})
        spec.setdefault("protected_hashes", {})
        spec["protected_hashes"] = result.protected_hashes
        session.exercise.grading_spec = spec
        session.exercise.save(update_fields=["grading_spec", "updated_at"])

    return result


def start_containers(session: WorkspaceSession) -> tuple[bool, str]:
    """Bring up an exercise's containers during the prepare phase.

    Deliberately called before the clock starts. ``--wait`` blocks on healthchecks so
    the user is never handed a workspace whose database is still initialising.

    Args:
        session: A scaffolded session.

    Returns:
        ``(ok, output)``. Output is returned on success too, since it is the
        diagnostic the user needs when a service comes up unhealthy.
    """
    if not session.workspace_path:
        return False, "This session has no workspace directory."
    workspace = Path(session.workspace_path)
    if not workspace.is_dir():
        return False, f"Workspace directory is missing: {workspace}"
    if not session.compose_project:
        return True, "This exercise declares no services."

    ok, output = docker_env.compose_up(session.compose_project, workspace)
    WorkspaceEvent.log(
        session,
        WorkspaceEvent.Kind.CONTAINERS_UP if ok else WorkspaceEvent.Kind.CONTAINERS_FAILED,
        output=output[-2000:],
    )
    return ok, output


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string.

    Small helper so callers building manifest-style dates do not each reimplement it.
    """
    return datetime.now(tz=timezone.utc).isoformat()
