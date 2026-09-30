"""Content hashing for exercises and templates.

Deliberately the **only** definition of these hashes, computed by exactly one
caller (the seed command). ``apps/coding`` has two disagreeing definitions of its
dedup hash -- ``description[:200]`` in ``save_challenges`` versus
``description[:500]`` in ``CodingChallenge.save`` -- which means its dedup silently
depends on which code path ran. Not repeating that here.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def exercise_hash(slug: str, base_app: str, mutation_digest: str) -> str:
    """Return a stable identity hash for an authored exercise.

    Args:
        slug: The exercise slug.
        base_app: The base application it is built on.
        mutation_digest: Hash of the mutation patches that define its defect.

    Returns:
        A hex SHA-256 digest.
    """
    payload = f"{slug}|{base_app}|{mutation_digest}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
    """Return the hex SHA-256 of one file's bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65_536), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_checksum(root: Path, *, skip_names: frozenset[str] = frozenset()) -> str:
    """Return a checksum over an entire directory tree.

    Computed over sorted ``(relative_path, file_digest)`` pairs, so it is stable
    across filesystems and independent of directory iteration order. Stored on the
    exercise and compared during verification, which is how an unintended template
    edit becomes visible rather than silently changing every future scaffold.

    Args:
        root: The directory to checksum.
        skip_names: File or directory names to ignore anywhere in the tree.

    Returns:
        A hex SHA-256 digest.
    """
    ignored = frozenset({"__pycache__", ".DS_Store", ".git", ".pytest_cache"}) | skip_names
    entries: list[str] = []
    for path in sorted(root.rglob("*")):
        if any(part in ignored for part in path.parts):
            continue
        if not path.is_file():
            continue
        entries.append(f"{path.relative_to(root).as_posix()}:{file_digest(path)}")

    digest = hashlib.sha256()
    for entry in entries:
        digest.update(entry.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def mutation_digest(patch_paths: list[Path]) -> str:
    """Return a checksum over an exercise's mutation patches.

    Args:
        patch_paths: The patch files, in application order.

    Returns:
        A hex SHA-256 digest, or the digest of the empty string if there are none.
    """
    digest = hashlib.sha256()
    for path in patch_paths:
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()
