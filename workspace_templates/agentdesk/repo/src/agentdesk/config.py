"""Settings, read from the environment once at import.

Everything here has a default that works in the container, so a fresh clone runs without
a ``.env``. The only value you are likely to change while working is ``AGENTDESK_POOL_MAX``,
and it is worth knowing why it is as small as it is -- see :data:`Settings.pool_max`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Resolved configuration.

    Attributes:
        database_url: libpq connection string for the ticket store.
        root: Repository root, used to find ``fixtures/`` and ``db/migrations/``.
        model: Model identifier. Part of every cassette key, so changing it invalidates
            the whole recorded set -- which is the intent, since a different model is a
            different set of answers.
        pool_max: Maximum pooled connections.

            **Deliberately 10, and deliberately not larger.** A generous pool hides the
            bug where a connection is held across a model call: with 200 connections you
            need 200 concurrent assistant requests before the desk notices. Production
            runs 10 per worker because the database has a connection limit too, and that
            is the number this repository is tuned to survive.
        max_agent_steps: Hard ceiling on tool-calling rounds in one run.
        vram_bytes: The serving planner's memory budget. Named in bytes rather than "GB"
            so no conversion is implied anywhere; see ``serving.memory``.
    """

    database_url: str
    root: Path
    model: str
    pool_max: int
    max_agent_steps: int
    vram_bytes: int

    @property
    def cassette_dir(self) -> Path:
        """Directory holding the recorded model responses."""
        return self.root / "fixtures" / "llm_cassettes"

    @property
    def migrations_dir(self) -> Path:
        """Directory holding the numbered SQL migrations."""
        return self.root / "db" / "migrations"

    @property
    def fixtures_dir(self) -> Path:
        """Directory holding seed data and the recording transcript."""
        return self.root / "fixtures"


@lru_cache(maxsize=1)
def _load() -> Settings:
    return Settings(
        database_url=os.environ.get(
            "DATABASE_URL",
            "postgresql://agentdesk:agentdesk@db:5432/agentdesk",
        ),
        root=Path(os.environ.get("AGENTDESK_ROOT", "/app")),
        model=os.environ.get("AGENTDESK_MODEL", "desk-8b-instruct"),
        pool_max=int(os.environ.get("AGENTDESK_POOL_MAX", "10")),
        max_agent_steps=int(os.environ.get("AGENTDESK_MAX_STEPS", "6")),
        # 24 GiB: one commodity accelerator. Small enough that the admission policy has
        # to say no sometimes, which is the only way the policy gets tested at all.
        vram_bytes=int(os.environ.get("AGENTDESK_VRAM_BYTES", str(24 * 1024**3))),
    )


#: Process-wide settings.
SETTINGS: Settings = _load()
