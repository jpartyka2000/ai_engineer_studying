"""Capture a session's work from disk, without disturbing it.

The central constraint: capturing a submission must not mutate the user's branch,
HEAD, index, or working tree. A naive ``git add -A`` would stage their files; a
``git stash`` would move their work. Instead this module writes a throwaway index
to a temp file, builds a tree from it, and attaches that tree to a detached commit
under ``refs/submissions/<id>`` -- leaving everything the user can see untouched.

The primary grading artifact is a unified diff of that snapshot against the seed
commit. It unifies committed, staged and unstaged work into the single coherent
patch a human reviewer would read, and it is trivially bounded in size. A full
directory walk would sweep in ``.venv/`` and ``node_modules/``; a git bundle alone
cannot be fed to a model.
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from apps.workspace.exceptions import CaptureError, GitCommandError
from apps.workspace.services import git_ops

logger = logging.getLogger(__name__)

# Never worth a grader's attention, and cheap to drop at the git level.
DEFAULT_DIFF_EXCLUDES: Final[tuple[str, ...]] = (
    "*.lock",
    "package-lock.json",
    "*.pyc",
    "__pycache__/*",
    "**/__pycache__/**",
    ".venv/*",
    "venv/*",
    "node_modules/*",
    ".pytest_cache/*",
    ".ruff_cache/*",
    "*.duckdb",
    "*.sqlite3",
    "*.parquet",
    "*.whl",
    ".grading/*",
)

# commit-tree needs an identity, and the user's global config is disabled.
CAPTURE_IDENTITY: Final[dict[str, str]] = {
    "GIT_AUTHOR_NAME": "AI Interview Prep",
    "GIT_AUTHOR_EMAIL": "harness@ai-interview-prep.local",
    "GIT_COMMITTER_NAME": "AI Interview Prep",
    "GIT_COMMITTER_EMAIL": "harness@ai-interview-prep.local",
}

SUBMISSION_REF_PREFIX: Final[str] = "refs/submissions"


@dataclass
class FileChange:
    """One changed file, as reported by ``git diff --numstat``."""

    path: str
    added: int
    deleted: int
    status: str = "M"

    @property
    def total(self) -> int:
        """Lines added plus deleted."""
        return self.added + self.deleted


@dataclass
class CaptureResult:
    """Everything captured from a workspace at submit time."""

    ok: bool = True
    error: str = ""
    snapshot_ref: str = ""
    snapshot_sha: str = ""
    seed_sha: str = ""

    diff_text: str = ""
    #: Complete inventory of changes, computed WITHOUT exclusions so the grader
    #: always knows what it did not see.
    numstat: list[FileChange] = field(default_factory=list)
    full_files: dict[str, str] = field(default_factory=dict)

    git_log: str = ""
    user_commit_count: int = 0
    branches: list[str] = field(default_factory=list)
    porcelain_status: str = ""
    untracked_paths: list[str] = field(default_factory=list)
    bundle_path: str = ""

    @property
    def files_changed(self) -> int:
        """Number of files touched."""
        return len(self.numstat)

    @property
    def lines_added(self) -> int:
        """Total lines added across all files."""
        return sum(change.added for change in self.numstat)

    @property
    def lines_deleted(self) -> int:
        """Total lines deleted across all files."""
        return sum(change.deleted for change in self.numstat)

    @property
    def is_empty(self) -> bool:
        """Whether nothing at all was submitted.

        Drives the empty-submission grading gate. Note it is *not* simply "no
        commits": working in a dirty tree without committing is still work.
        """
        return not self.numstat and self.user_commit_count == 0


def submission_ref(session_id: int) -> str:
    """Return the ref name used to pin a session's snapshot."""
    return f"{SUBMISSION_REF_PREFIX}/{session_id}"


def _exclude_pathspecs(extra_excludes: list[str] | None = None) -> list[str]:
    """Build git pathspec arguments that drop uninteresting files.

    Uses native git ``:(exclude)`` pathspecs rather than filtering in Python, so
    no ``pathspec`` dependency is needed and the exclusion happens before git
    generates the diff at all.
    """
    patterns = list(DEFAULT_DIFF_EXCLUDES) + list(extra_excludes or [])
    return ["--", "."] + [f":(exclude){pattern}" for pattern in patterns]


def snapshot_work(workspace: Path, session_id: int) -> tuple[str, str]:
    """Snapshot the full working tree without touching the user's git state.

    Uses a throwaway ``GIT_INDEX_FILE`` so the user's real index is never
    modified, then ``write-tree`` + ``commit-tree`` to produce a commit that is
    reachable only from a private ref.

    Args:
        workspace: The workspace repository.
        session_id: Session primary key, used to name the ref.

    Returns:
        ``(ref_name, commit_sha)``.

    Raises:
        CaptureError: If the snapshot cannot be created.
    """
    ref = submission_ref(session_id)
    try:
        with tempfile.TemporaryDirectory(prefix="aiprep-index-") as tmp:
            index_env = dict(CAPTURE_IDENTITY)
            index_env["GIT_INDEX_FILE"] = str(Path(tmp) / "index")

            # Starts from an empty index, so this stages the whole worktree
            # (minus .gitignore'd paths) without touching the user's index.
            git_ops.run_git(workspace, "add", "-A", env_extra=index_env)
            tree = git_ops.run_git(workspace, "write-tree", env_extra=index_env)
            commit = git_ops.run_git(
                workspace,
                "commit-tree",
                tree,
                "-p",
                "HEAD",
                "-m",
                f"submission snapshot for session {session_id}",
                env_extra=index_env,
            )
        git_ops.run_git(workspace, "update-ref", ref, commit)
    except GitCommandError as exc:
        raise CaptureError(f"Could not snapshot work in {workspace}: {exc}") from exc
    return ref, commit


def _parse_numstat(raw: str) -> list[FileChange]:
    """Parse ``git diff --numstat`` output into :class:`FileChange` records.

    Binary files report ``-`` instead of counts; those become zeros so the file is
    still listed rather than silently dropped.
    """
    changes: list[FileChange] = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added_raw, deleted_raw, path = parts[0], parts[1], parts[-1]
        added = 0 if added_raw == "-" else int(added_raw or 0)
        deleted = 0 if deleted_raw == "-" else int(deleted_raw or 0)
        changes.append(FileChange(path=path, added=added, deleted=deleted))
    return changes


def _read_full_files(workspace: Path, ref: str, paths: list[str]) -> dict[str, str]:
    """Read whole files out of the snapshot, for paths grading needs in full.

    Reads from the snapshot ref rather than the working tree so the content is
    guaranteed to match the diff.
    """
    contents: dict[str, str] = {}
    for path in paths:
        try:
            # run_git_raw, not run_git: file content must not be rstripped.
            contents[path] = git_ops.run_git_raw(workspace, "show", f"{ref}:{path}")
        except GitCommandError:
            # Absent from the snapshot: the user may have deleted it, or it may
            # never have existed. Not an error worth failing the capture over.
            logger.debug("full-file read skipped for missing path %s", path)
    return contents


def capture(
    workspace: Path | str,
    *,
    session_id: int,
    seed_sha: str,
    extra_excludes: list[str] | None = None,
    include_full_files: list[str] | None = None,
    bundle_destination: Path | None = None,
) -> CaptureResult:
    """Capture a submission from a workspace directory.

    Never raises for an unusable workspace: a deleted directory or a broken repo
    yields ``ok=False`` with an explanatory error, so grading can still proceed on
    the user's written notes rather than returning a 500.

    Args:
        workspace: The workspace repository.
        session_id: Session primary key.
        seed_sha: The scaffold commit the diff is taken against.
        extra_excludes: Manifest-supplied exclusion patterns.
        include_full_files: Paths to include in full, not just as a diff.
        bundle_destination: Where to write a ``git bundle`` archive, if wanted.

    Returns:
        A :class:`CaptureResult`.
    """
    path = Path(workspace)
    result = CaptureResult(seed_sha=seed_sha)

    if not path.is_dir():
        result.ok = False
        result.error = f"Workspace directory no longer exists: {path}"
        return result
    if not git_ops.is_repo(path):
        result.ok = False
        result.error = f"Workspace is not a git repository: {path}"
        return result

    try:
        result.snapshot_ref, result.snapshot_sha = snapshot_work(path, session_id)
    except CaptureError as exc:
        result.ok = False
        result.error = str(exc)
        return result

    ref = result.snapshot_ref
    try:
        # The diff the grader reads: exclusions applied, rename detection on,
        # external diff drivers disabled (a global diff.external would otherwise
        # produce unusable output).
        result.diff_text = git_ops.run_git(
            path,
            "diff",
            "--no-color",
            "--no-ext-diff",
            "-M",
            "-U5",
            seed_sha,
            ref,
            *_exclude_pathspecs(extra_excludes),
            timeout=120,
        )

        # Deliberately WITHOUT exclusions: this inventory must stay complete even
        # when the diff itself is trimmed, so truncation is never invisible.
        result.numstat = _parse_numstat(
            git_ops.run_git(
                path, "diff", "--numstat", "--no-ext-diff", "-M", seed_sha, ref, timeout=120
            )
        )

        # Full bodies, not just subjects: the "why" lives in the body, and commit
        # messages are a scored part of the documentation dimension.
        result.git_log = git_ops.run_git(
            path, "log", "--no-color", "--format=%h %an %ad%n%B%n---", f"{seed_sha}..HEAD"
        )
        result.user_commit_count = git_ops.commit_count(path, since=seed_sha)
        result.branches = [
            line.strip().lstrip("* ").strip()
            for line in git_ops.run_git(path, "branch", "--all", "--no-color").splitlines()
            if line.strip()
        ]
        result.porcelain_status = git_ops.run_git(path, "status", "--porcelain")
        result.untracked_paths = [
            line[3:] for line in result.porcelain_status.splitlines() if line.startswith("?? ")
        ]

        if include_full_files:
            result.full_files = _read_full_files(path, ref, include_full_files)

        if bundle_destination is not None:
            bundle_destination.parent.mkdir(parents=True, exist_ok=True)
            git_ops.run_git(
                path,
                "bundle",
                "create",
                str(bundle_destination),
                "--all",
                ref,
                timeout=180,
            )
            result.bundle_path = str(bundle_destination)
    except GitCommandError as exc:
        # Partial capture is still useful; record what went wrong and keep going.
        result.ok = False
        result.error = str(exc)
        logger.warning("partial capture for session %s: %s", session_id, exc)

    return result


def relevance_order(
    changes: list[FileChange],
    *,
    focus_paths: list[str] | None = None,
    check_paths: list[str] | None = None,
) -> list[FileChange]:
    """Order changed files by how much the grader needs to see them.

    Alphabetical order is actively harmful when a diff must be trimmed: it would
    drop the file the exercise is about because its name starts with "s".

    Args:
        changes: The files to order.
        focus_paths: Authored paths where the work belongs. Highest priority.
        check_paths: Paths referenced by acceptance checks. Next highest.

    Returns:
        The same records, most relevant first.
    """
    focus = tuple(focus_paths or ())
    checks = tuple(check_paths or ())

    def rank(change: FileChange) -> tuple[int, str]:
        path = change.path
        if any(path.startswith(prefix) or path == prefix for prefix in focus):
            return (0, path)
        if any(path.startswith(prefix) or path == prefix for prefix in checks):
            return (1, path)
        if path.startswith("tests/") or "/tests/" in path:
            return (3, path)
        if path.endswith((".md", ".rst", ".txt")):
            return (4, path)
        return (2, path)

    return sorted(changes, key=rank)
