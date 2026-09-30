"""Filesystem safety kernel for workspace mode.

This module is the only place in the project that deletes a directory tree, and
every path the app writes to passes through ``assert_safe_workspace_path`` first.
It exists because workspace mode materializes real repositories onto the user's
disk and later removes them -- an operation that is unforgiving of an off-by-one
in a path calculation.

Two independent gates protect deletion:

1. **Containment** (:func:`assert_safe_workspace_path`) -- the path must resolve
   to somewhere strictly inside ``settings.WORKSPACE_ROOT``, that root must not
   be a dangerous location like ``/`` or the user's home directory, and no
   component of the path may be a symlink.
2. **Provenance** (:func:`assert_deletable`) -- the directory must carry the
   sentinel file this app wrote, proving we created it, and its owning session
   must not still be running.

A directory that fails either gate is never touched, even if that means leaving
an orphan behind. Leaking a directory is recoverable; deleting the wrong one is
not.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Container
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from django.conf import settings
from django.utils import timezone

from apps.workspace.exceptions import NotDeletableError, UnsafePathError

# Bumped if the sentinel's JSON shape ever changes, so an old sentinel can be
# recognised rather than misparsed.
SENTINEL_SCHEMA_VERSION: Final[int] = 1

# Marks a sentinel as belonging to this application specifically, so a
# same-named file from something else is not mistaken for ours.
SENTINEL_APP_ID: Final[str] = "ai_interview_prep.workspace"

# A workspace root must be at least this deep. "/" has 1 part and "/Users" has
# 2; requiring 3 rules out an accidentally-configured top-level directory.
MIN_ROOT_PARTS: Final[int] = 3


def workspace_root() -> Path:
    """Return the resolved root directory that contains all workspaces.

    Returns:
        The absolute, symlink-resolved ``settings.WORKSPACE_ROOT``.
    """
    return Path(settings.WORKSPACE_ROOT).expanduser().resolve()


def template_root() -> Path:
    """Return the directory holding the authored exercise templates."""
    return Path(settings.WORKSPACE_TEMPLATE_ROOT).expanduser().resolve()


def archive_root() -> Path:
    """Return the directory finished workspaces are moved into."""
    return workspace_root() / settings.WORKSPACE_ARCHIVE_DIRNAME


def origins_root() -> Path:
    """Return the directory holding bare "origin" repos that emulate GitHub."""
    return workspace_root() / settings.WORKSPACE_ORIGINS_DIRNAME


def sentinel_path(workspace: Path) -> Path:
    """Return the sentinel file path for a workspace directory."""
    return workspace / settings.WORKSPACE_SENTINEL_FILENAME


def session_dir_name(exercise_number: int, slug: str) -> str:
    """Build the on-disk directory name for a session's workspace.

    Args:
        exercise_number: The exercise's stable 1-50 number.
        slug: The exercise slug, e.g. ``"ex-017-tenant-isolation"``.

    Returns:
        A directory name such as ``"ex-017-tenant-isolation"``. The number is
        zero-padded so the directory listing sorts naturally.
    """
    tail = slug
    prefix = f"ex-{exercise_number:03d}-"
    # Authored slugs already start with their number; don't double it up.
    if slug.startswith(prefix):
        return slug
    if slug.startswith("ex-"):
        tail = slug.split("-", 2)[-1]
    return f"{prefix}{tail}"


def _assert_root_is_sane(root: Path) -> None:
    """Validate the configured workspace root itself.

    A misconfigured root is the most dangerous failure mode here: if it were
    ``/`` or the user's home directory, every other containment check would
    still pass while permitting catastrophic deletion.

    Raises:
        UnsafePathError: If the root is not a safe place to manage directories.
    """
    if not root.is_absolute():
        raise UnsafePathError(f"WORKSPACE_ROOT must be absolute, got {root!r}")
    if root == Path(root.anchor):
        raise UnsafePathError(f"WORKSPACE_ROOT must not be the filesystem root, got {root!r}")
    if root == Path.home().resolve():
        raise UnsafePathError(f"WORKSPACE_ROOT must not be the home directory, got {root!r}")
    if root == Path(settings.BASE_DIR).resolve():
        raise UnsafePathError(f"WORKSPACE_ROOT must not be the project directory, got {root!r}")
    if len(root.parts) < MIN_ROOT_PARTS:
        raise UnsafePathError(
            f"WORKSPACE_ROOT is suspiciously shallow ({len(root.parts)} components): {root!r}"
        )


def _assert_no_symlinked_component(raw: Path, root: Path) -> None:
    """Reject the path if any component between ``root`` and ``raw`` is a symlink.

    ``Path.resolve()`` silently *follows* symlinks, which would turn an
    ``ex-001 -> /`` symlink into a successful resolution somewhere unexpected.
    Containment catches the escaping case, but a symlink pointing at a sibling
    workspace would stay inside the root and pass. Treat any symlink on the
    chain as an error instead.

    Raises:
        UnsafePathError: If a symlinked component is found.
    """
    try:
        relative = raw.relative_to(root)
    except ValueError:
        # Not under the root at all; containment reports this with a better message.
        return
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise UnsafePathError(f"Refusing to operate on {raw}: component {current} is a symlink")


def assert_safe_workspace_path(path: Path | str) -> Path:
    """Assert that ``path`` is a location this app may create or modify.

    Args:
        path: An absolute path expected to live inside the workspace root.

    Returns:
        The resolved, validated path.

    Raises:
        UnsafePathError: If the path escapes the workspace root, *is* the root,
            traverses a symlink, contains ``..``, or the root itself is unsafe.
    """
    original = str(path)
    if ".." in Path(original).parts:
        raise UnsafePathError(f"Refusing to operate on a path containing '..': {original!r}")

    root = workspace_root()
    _assert_root_is_sane(root)

    raw = Path(original).expanduser()
    if not raw.is_absolute():
        raise UnsafePathError(f"Workspace paths must be absolute, got {original!r}")

    _assert_no_symlinked_component(raw, root)

    resolved = raw.resolve()
    if not resolved.is_relative_to(root):
        raise UnsafePathError(f"Refusing to operate outside {root}: {resolved}")
    if resolved == root:
        raise UnsafePathError(f"Refusing to operate on the workspace root itself: {root}")
    return resolved


def write_sentinel(
    workspace: Path,
    *,
    session_id: int,
    exercise_slug: str,
    created_at: datetime | None = None,
) -> Path:
    """Write the sentinel file that marks a directory as ours to manage.

    Args:
        workspace: The workspace directory, which must already exist.
        session_id: Primary key of the owning ``WorkspaceSession``.
        exercise_slug: Slug of the exercise being scaffolded.
        created_at: Creation timestamp; defaults to now.

    Returns:
        The path to the sentinel file that was written.
    """
    target = assert_safe_workspace_path(workspace)
    payload = {
        "schema_version": SENTINEL_SCHEMA_VERSION,
        "app": SENTINEL_APP_ID,
        "session_id": session_id,
        "exercise_slug": exercise_slug,
        "created_at": (created_at or timezone.now()).isoformat(),
    }
    destination = sentinel_path(target)
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return destination


def read_sentinel(workspace: Path) -> dict[str, Any] | None:
    """Read and validate a workspace's sentinel file.

    Args:
        workspace: The workspace directory to inspect.

    Returns:
        The parsed sentinel payload, or ``None`` if it is absent, unreadable,
        malformed, or was written by something other than this app.
    """
    target = assert_safe_workspace_path(workspace)
    source = sentinel_path(target)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("app") != SENTINEL_APP_ID:
        return None
    return payload


def assert_deletable(
    path: Path | str,
    *,
    active_session_ids: Container[int] | None = None,
) -> Path:
    """Assert that a directory may be deleted.

    Containment alone is not enough: the directory must also be one *we* created.
    Without the sentinel requirement, a user who pointed ``WORKSPACE_ROOT`` at a
    directory holding their own work would lose it.

    Args:
        path: The directory to delete.
        active_session_ids: Sessions that are still running. If the sentinel's
            session appears here, deletion is refused. Callers that track
            session state should always pass this.

    Returns:
        The resolved, validated path.

    Raises:
        UnsafePathError: If the path fails the containment checks.
        NotDeletableError: If the directory is missing, carries no valid
            sentinel, or belongs to a running session.
    """
    target = assert_safe_workspace_path(path)
    if not target.is_dir():
        raise NotDeletableError(f"Not a directory: {target}")

    sentinel = read_sentinel(target)
    if sentinel is None:
        raise NotDeletableError(
            f"Refusing to delete {target}: no {settings.WORKSPACE_SENTINEL_FILENAME} "
            "sentinel, so this app did not create it"
        )

    session_id = sentinel.get("session_id")
    if active_session_ids is not None and session_id in active_session_ids:
        raise NotDeletableError(
            f"Refusing to delete {target}: session {session_id} is still running"
        )
    return target


def destroy(path: Path | str, *, active_session_ids: Container[int] | None = None) -> Path:
    """Recursively delete a workspace directory.

    This is the only ``shutil.rmtree`` call site in the project. Route every
    deletion through it so both safety gates are always applied.

    Args:
        path: The directory to delete.
        active_session_ids: Sessions that are still running; see
            :func:`assert_deletable`.

    Returns:
        The path that was deleted.

    Raises:
        UnsafePathError: If the path fails the containment checks.
        NotDeletableError: If the directory is not eligible for deletion.
    """
    target = assert_deletable(path, active_session_ids=active_session_ids)
    shutil.rmtree(target)
    return target


def safe_join(base: Path | str, user_relative: str) -> Path:
    """Resolve a user-supplied relative path against a workspace directory.

    Guards the read-only file-preview endpoint. Without this, a request for
    ``?path=../../../../etc/passwd`` would read arbitrary files off disk through
    the user's own dev server.

    Args:
        base: The workspace directory the path must stay inside.
        user_relative: An untrusted relative path from a query parameter.

    Returns:
        The resolved absolute path, guaranteed to be inside ``base``.

    Raises:
        UnsafePathError: If the result escapes ``base``, is absolute, contains
            ``..``, or traverses a symlink.
    """
    root = assert_safe_workspace_path(base)

    candidate = Path(user_relative)
    if candidate.is_absolute():
        raise UnsafePathError(f"Path must be relative, got {user_relative!r}")
    if ".." in candidate.parts:
        raise UnsafePathError(f"Path must not contain '..', got {user_relative!r}")

    joined = root / candidate
    _assert_no_symlinked_component(joined, root)

    resolved = joined.resolve()
    if not resolved.is_relative_to(root):
        raise UnsafePathError(f"Path escapes {root}: {user_relative!r}")
    return resolved
