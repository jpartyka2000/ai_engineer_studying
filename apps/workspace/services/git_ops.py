"""Git plumbing for workspace mode.

Every git invocation in this app goes through :func:`run_git`, which runs with the
user's global and system git configuration **disabled**. That is not paranoia: a
global ``commit.gpgsign = true``, a ``core.hooksPath``, a ``diff.external``, or an
``init.templateDir`` will each break history seeding or work capture in ways that
are extremely hard to diagnose from the failure message alone.

The app itself is not sandboxed -- it is a local development server managing
directories on the user's own machine -- so ``subprocess`` is the right tool here.
That is a deliberate contrast with ``apps/coding/services/code_runner.py``, which
executes untrusted submitted code and therefore needs Docker isolation.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Final

from django.conf import settings

from apps.workspace.exceptions import GitCommandError

logger = logging.getLogger(__name__)

# Environment that neutralises anything the user has configured globally.
GIT_ENV_BASE: Final[dict[str, str]] = {
    # Ignore ~/.gitconfig and /etc/gitconfig entirely.
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    # Never block waiting for credentials; all of our remotes are local paths.
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "",
    # Never page output.
    "GIT_PAGER": "cat",
    "PAGER": "cat",
    # Stable, parseable messages and sort order.
    "LC_ALL": "C",
    "LANG": "C",
}

# Applied as `-c key=value` before every subcommand.
GIT_CONFIG_OVERRIDES: Final[tuple[str, ...]] = (
    "commit.gpgsign=false",
    "tag.gpgsign=false",
    "core.autocrlf=false",
    "core.hooksPath=/dev/null",
    "init.defaultBranch=main",
    "advice.detachedHead=false",
    "core.quotepath=false",
)

#: `:(exclude)` pathspecs need 2.13; `init.defaultBranch` needs 2.28.
MIN_GIT_VERSION: Final[tuple[int, int]] = (2, 28)

_VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


def _git_env(env_extra: dict[str, str] | None = None) -> dict[str, str]:
    """Build the environment for a git subprocess.

    Args:
        env_extra: Extra variables to add, e.g. ``GIT_AUTHOR_DATE`` when seeding
            backdated history, or ``GIT_INDEX_FILE`` when capturing work.

    Returns:
        A copy of the current environment with the git-neutralising overrides
        applied on top.
    """
    env = os.environ.copy()
    env.update(GIT_ENV_BASE)
    if env_extra:
        env.update(env_extra)
    return env


def run_git(
    cwd: Path | str,
    *args: str,
    env_extra: dict[str, str] | None = None,
    timeout: int | None = None,
    check: bool = True,
) -> str:
    """Run a git command and return its stdout.

    Args:
        cwd: Directory to run in. Passed via ``-C`` rather than ``subprocess``'s
            ``cwd`` so the failure message names the repository.
        *args: The subcommand and its arguments, e.g. ``"status", "--porcelain"``.
        env_extra: Extra environment variables for this call only.
        timeout: Seconds before the command is killed. Defaults to
            ``settings.WORKSPACE_GIT_TIMEOUT_SECONDS``.
        check: If ``True``, a non-zero exit raises. If ``False``, stdout is
            returned regardless, which is what callers want for commands whose
            exit code is itself the answer (``git check-ignore``, ``diff --quiet``).

    Returns:
        Stdout, with trailing whitespace stripped.

    Raises:
        GitCommandError: If git exits non-zero (and ``check``), times out, or is
            not installed.
    """
    command = ["git", "-C", str(cwd)]
    for override in GIT_CONFIG_OVERRIDES:
        command += ["-c", override]
    command += list(args)

    effective_timeout = timeout if timeout is not None else settings.WORKSPACE_GIT_TIMEOUT_SECONDS

    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            command,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            env=_git_env(env_extra),
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitCommandError("git is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitCommandError(
            f"git {' '.join(args)} timed out after {effective_timeout}s in {cwd}"
        ) from exc

    if check and completed.returncode != 0:
        raise GitCommandError(
            f"git {' '.join(args)} failed in {cwd} "
            f"(exit {completed.returncode}): {completed.stderr.strip()}"
        )
    return completed.stdout.rstrip()


def run_git_raw(
    cwd: Path | str,
    *args: str,
    env_extra: dict[str, str] | None = None,
    timeout: int | None = None,
) -> str:
    """Run a git command and return stdout **byte-for-byte**.

    :func:`run_git` strips trailing whitespace, which is right for parsing command
    output but wrong for file contents: reading a blob with ``git show`` through it
    would silently drop the file's final newline and any trailing blank lines. Use
    this whenever the output *is* content rather than a report.

    Args:
        cwd: Directory to run in.
        *args: The subcommand and its arguments.
        env_extra: Extra environment variables for this call only.
        timeout: Seconds before the command is killed.

    Returns:
        Stdout exactly as git produced it.

    Raises:
        GitCommandError: If git exits non-zero, times out, or is not installed.
    """
    command = ["git", "-C", str(cwd)]
    for override in GIT_CONFIG_OVERRIDES:
        command += ["-c", override]
    command += list(args)

    effective_timeout = timeout if timeout is not None else settings.WORKSPACE_GIT_TIMEOUT_SECONDS
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            command,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            env=_git_env(env_extra),
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitCommandError("git is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitCommandError(
            f"git {' '.join(args)} timed out after {effective_timeout}s in {cwd}"
        ) from exc

    if completed.returncode != 0:
        raise GitCommandError(
            f"git {' '.join(args)} failed in {cwd} "
            f"(exit {completed.returncode}): {completed.stderr.strip()}"
        )
    return completed.stdout


def run_git_status(cwd: Path | str, *args: str, timeout: int | None = None) -> int:
    """Run a git command and return only its exit code.

    For commands whose exit status is the answer, such as ``check-ignore``.

    Args:
        cwd: Directory to run in.
        *args: The subcommand and its arguments.
        timeout: Seconds before the command is killed.

    Returns:
        The process exit code.
    """
    command = ["git", "-C", str(cwd)]
    for override in GIT_CONFIG_OVERRIDES:
        command += ["-c", override]
    command += list(args)
    effective_timeout = timeout if timeout is not None else settings.WORKSPACE_GIT_TIMEOUT_SECONDS
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            command,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            env=_git_env(),
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise GitCommandError(f"git {' '.join(args)} could not run in {cwd}") from exc
    return completed.returncode


def git_version() -> tuple[int, int, int] | None:
    """Return the installed git version, or ``None`` if git is unavailable."""
    try:
        output = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            env=_git_env(),
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if output.returncode != 0:
        return None
    match = _VERSION_RE.search(output.stdout)
    if not match:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def git_available() -> tuple[bool, str]:
    """Check that git is installed and new enough.

    Returns:
        ``(ok, message)``. The message names the version found, or explains what
        is wrong, so it can be shown to the user directly.
    """
    version = git_version()
    if version is None:
        return False, "git is not installed or not on PATH"
    if version[:2] < MIN_GIT_VERSION:
        found = ".".join(str(part) for part in version)
        needed = ".".join(str(part) for part in MIN_GIT_VERSION)
        return False, f"git {found} is too old; {needed} or newer is required"
    return True, "git " + ".".join(str(part) for part in version)


def is_repo(path: Path | str) -> bool:
    """Return whether ``path`` is inside a git working tree."""
    try:
        return run_git(path, "rev-parse", "--is-inside-work-tree", check=False) == "true"
    except GitCommandError:
        return False


def head_sha(cwd: Path | str) -> str:
    """Return the full SHA of HEAD."""
    return run_git(cwd, "rev-parse", "HEAD")


def is_tree_clean(cwd: Path | str) -> bool:
    """Return whether the working tree has no changes, staged or otherwise.

    Asserted right after scaffolding: a dirty tree at T=0 would corrupt the
    diff-against-seed story that grading depends on.
    """
    return run_git(cwd, "status", "--porcelain") == ""


def commit_count(cwd: Path | str, since: str | None = None) -> int:
    """Count commits, optionally only those after ``since``.

    Args:
        cwd: The repository.
        since: A revision; when given, counts ``since..HEAD``.

    Returns:
        The number of commits.
    """
    spec = f"{since}..HEAD" if since else "HEAD"
    output = run_git(cwd, "rev-list", "--count", spec, check=False)
    try:
        return int(output.strip() or 0)
    except ValueError:
        return 0
