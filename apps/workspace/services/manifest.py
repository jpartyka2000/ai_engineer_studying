"""Loading and validating an exercise template's ``manifest.json``.

The manifest is the only machine-read file in a template. It is JSON rather than
YAML specifically so that no new dependency is needed -- ``pyyaml`` is not in
``requirements/base.txt``, and ``pip install`` has failed in this environment
before.

Validation is strict and happens at load time, because a manifest error discovered
during scaffolding costs the user time on the clock, while one discovered by the
verification command costs nothing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from apps.workspace.exceptions import ManifestError
from apps.workspace.schemas import Manifest
from apps.workspace.services import paths

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "manifest.json"
REPO_DIRNAME = "repo"
SEED_DIRNAME = "seed"
SOLUTION_DIRNAME = "solution"
COMMON_DIRNAME = "_common"
PATCHES_DIRNAME = "patches"
WHEELHOUSE_DIRNAME = "wheelhouse"

#: Directories under the template root that are not base apps.
NON_TEMPLATE_DIRS = frozenset({COMMON_DIRNAME, PATCHES_DIRNAME, WHEELHOUSE_DIRNAME})


def template_dir(template_name: str) -> Path:
    """Return the directory holding a base app's template.

    Args:
        template_name: The template directory name, e.g. ``"tenantsaas"``.

    Returns:
        The absolute path.

    Raises:
        ManifestError: If the directory does not exist.
    """
    candidate = paths.template_root() / template_name
    if not candidate.is_dir():
        raise ManifestError(f"Template directory not found: {candidate}")
    return candidate


def repo_dir(template_name: str) -> Path:
    """Return the pristine working tree inside a template.

    Raises:
        ManifestError: If the ``repo/`` directory is missing.
    """
    candidate = template_dir(template_name) / REPO_DIRNAME
    if not candidate.is_dir():
        raise ManifestError(f"Template {template_name!r} has no {REPO_DIRNAME}/ directory")
    return candidate


def load_manifest(template_name: str) -> Manifest:
    """Load and validate a template's manifest.

    Args:
        template_name: The template directory name.

    Returns:
        The validated :class:`~apps.workspace.schemas.Manifest`.

    Raises:
        ManifestError: If the file is missing, unparseable, or fails validation.
    """
    source = template_dir(template_name) / MANIFEST_FILENAME
    if not source.is_file():
        raise ManifestError(f"No {MANIFEST_FILENAME} in template {template_name!r}")

    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ManifestError(f"{source} is not valid JSON: {exc}") from exc

    try:
        return Manifest.model_validate(payload)
    except ValidationError as exc:
        raise ManifestError(f"{source} failed validation:\n{exc}") from exc


def validate_template(template_name: str) -> list[str]:
    """Check a template for the problems that break scaffolding.

    Returns findings rather than raising, so the verification command can report
    every problem across all templates in one pass instead of stopping at the first.

    Args:
        template_name: The template directory name.

    Returns:
        A list of human-readable problems. Empty means the template is sound.
    """
    problems: list[str] = []

    try:
        manifest = load_manifest(template_name)
    except ManifestError as exc:
        return [str(exc)]

    try:
        repo = repo_dir(template_name)
    except ManifestError as exc:
        return [str(exc)]

    root = template_dir(template_name)

    # A committed .git would become a gitlink and break history seeding entirely.
    if (repo / ".git").exists():
        problems.append(f"{template_name}: repo/ must not contain a .git directory")
    # A committed .env would leak into the seed history; the real one is generated.
    if (repo / ".env").exists():
        problems.append(
            f"{template_name}: repo/ must ship .env.example only; .env is generated "
            "at scaffold time so the user's tree is clean at T=0"
        )

    # Every file must belong to exactly one seed commit, or it would sit untracked
    # in the user's brand-new workspace and pollute the diff baseline.
    declared: set[str] = set()
    for index, commit in enumerate(manifest.seed_commits):
        for entry in commit.paths:
            target = repo / entry
            if not target.exists():
                problems.append(
                    f"{template_name}: seed_commits[{index}] references missing path {entry!r}"
                )
            declared.add(entry.rstrip("/"))

    covered: set[Path] = set()
    for entry in declared:
        target = repo / entry
        if target.is_dir():
            covered.update(p for p in target.rglob("*") if p.is_file())
        elif target.is_file():
            covered.add(target)

    all_files = {
        p
        for p in repo.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.name != ".DS_Store"
    }
    orphans = sorted(str(p.relative_to(repo)) for p in all_files - covered)
    if orphans:
        problems.append(
            f"{template_name}: {len(orphans)} file(s) are in repo/ but not in any "
            f"seed commit, so they would start untracked: {orphans[:10]}"
        )

    # Declared DB seed directories must exist.
    for service, relative in manifest.db_seeds.items():
        if not (root / relative).exists():
            problems.append(
                f"{template_name}: db_seeds[{service!r}] points at missing path {relative!r}"
            )

    # A port must be declared for every service the compose file publishes.
    if manifest.ports and not (repo / "docker-compose.yml").is_file():
        problems.append(
            f"{template_name}: manifest declares ports {sorted(manifest.ports)} but "
            "repo/docker-compose.yml is missing"
        )

    # The reference solution must never be shipped into a workspace.
    solution = root / SOLUTION_DIRNAME
    if solution.exists() and not solution.is_dir():
        problems.append(f"{template_name}: {SOLUTION_DIRNAME} must be a directory")

    return problems


def common_dir() -> Path | None:
    """Return the shared skeleton directory merged into every template.

    Returns:
        The ``_common`` directory, or ``None`` if it has not been created yet.
    """
    candidate = paths.template_root() / COMMON_DIRNAME
    return candidate if candidate.is_dir() else None


def list_templates() -> list[str]:
    """Return the names of every available base app template, sorted."""
    root = paths.template_root()
    if not root.is_dir():
        return []
    return sorted(
        child.name
        for child in root.iterdir()
        if child.is_dir() and child.name not in NON_TEMPLATE_DIRS and not child.name.startswith(".")
    )
