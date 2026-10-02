"""Configuration, read from the environment exactly once.

Two stores, two settings groups, and a deliberate asymmetry between them.

**Mongo is addressed by URL** because it is a server the process connects to, and in
every environment except a developer's laptop that URL is something the platform hands
us. **DuckDB is addressed by path** because it is a library and the warehouse is a file;
there is no server, no port and no credential.

Nothing here reads the environment at import time except :data:`SETTINGS`, and a test
that needs different settings constructs its own :class:`Settings` rather than mutating
``os.environ`` -- which is what keeps the suite parallelisable and order-independent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

#: Service root, overridable so tests can point the warehouse at a scratch tree.
PROJECT_ROOT = Path(os.environ.get("EVENTSTORE_ROOT", Path(__file__).resolve().parents[2]))

#: Apdex target in milliseconds. The product SLO, not a tuning knob: changing it
#: changes what every historical score meant, so it lives here with a comment rather
#: than in a dashboard.
APDEX_TARGET_MS = 300.0

#: How far back the operational "recent" endpoint will look. Mongo holds the full event
#: stream, but a query without an upper bound on its range is a query that gets slower
#: every day the service runs.
MAX_RECENT_MINUTES = 1440

#: Default rollup grain. Minute buckets keep the analytical tables small enough to scan
#: and fine enough to see a deploy.
ROLLUP_GRAIN_SECONDS = 60


@dataclass(frozen=True)
class Settings:
    """Everything the service needs to know about where its data lives.

    Attributes:
        mongo_url: Connection string for the operational store.
        mongo_database: Database name inside that server.
        root: Service root, from which the warehouse path is derived.
        apdex_target_ms: Apdex target ``T``.
        bootstrap_seed: Seed used for every bootstrap interval the API reports, so
            that two requests for the same window return the same interval.
    """

    mongo_url: str = "mongodb://db:27017"
    mongo_database: str = "eventstore"
    root: Path = field(default_factory=lambda: PROJECT_ROOT)
    apdex_target_ms: float = APDEX_TARGET_MS
    bootstrap_seed: int = 20260401

    @property
    def warehouse_dir(self) -> Path:
        """Directory holding the DuckDB file."""
        return self.root / "warehouse"

    @property
    def warehouse_path(self) -> Path:
        """The DuckDB database file itself."""
        return self.warehouse_dir / "eventstore.duckdb"

    def ensure_dirs(self) -> Settings:
        """Create the directories a run needs. Returns self."""
        self.warehouse_dir.mkdir(parents=True, exist_ok=True)
        return self


def settings_from_env(**overrides: object) -> Settings:
    """Build settings from the environment, with explicit overrides on top.

    Args:
        **overrides: Field values that win over the environment. Tests use this
            instead of patching ``os.environ``.

    Returns:
        A :class:`Settings`.
    """
    base = {
        "mongo_url": os.environ.get("MONGO_URL", "mongodb://db:27017"),
        "mongo_database": os.environ.get("MONGO_DATABASE", "eventstore"),
        "root": Path(os.environ.get("EVENTSTORE_ROOT", str(PROJECT_ROOT))),
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


#: Process-wide settings. Imported by the API and the CLI; never by ``perfmodel``.
SETTINGS = settings_from_env()
