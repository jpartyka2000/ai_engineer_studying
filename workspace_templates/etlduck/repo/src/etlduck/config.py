"""Paths and tunables for the warehouse.

Every path is resolved from one root so a test can point the whole pipeline at a
temporary directory by setting a single environment variable. Hardcoding paths module by
module is what makes an ETL codebase impossible to test without clobbering real data.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

#: Project root, overridable so tests can run against a scratch tree.
PROJECT_ROOT = Path(os.environ.get("ETLDUCK_ROOT", Path(__file__).resolve().parents[2]))

#: Quality thresholds. Named rather than inlined so a job overriding one is making a
#: visible choice, and so the numbers can be cited in a review.
MAX_QUARANTINE_FRACTION = 0.05
MIN_ACCOUNTS_EXPECTED = 5


@dataclass(frozen=True)
class Paths:
    """Where everything lives, derived from one root."""

    root: Path

    @property
    def raw(self) -> Path:
        """Landing zone: whatever the upstream export dropped, untouched."""
        return self.root / "raw"

    @property
    def warehouse(self) -> Path:
        """Directory holding the DuckDB file."""
        return self.root / "warehouse"

    @property
    def database(self) -> Path:
        """The DuckDB database file itself."""
        return self.warehouse / "etlduck.duckdb"

    def ensure(self) -> Paths:
        """Create the directories that must exist before a run. Returns self."""
        self.raw.mkdir(parents=True, exist_ok=True)
        self.warehouse.mkdir(parents=True, exist_ok=True)
        return self


def paths(root: str | Path | None = None) -> Paths:
    """Return the path set for a root, defaulting to the project root.

    Args:
        root: Override the root directory. Used by tests.

    Returns:
        A :class:`Paths`.
    """
    return Paths(root=Path(root) if root is not None else PROJECT_ROOT)
