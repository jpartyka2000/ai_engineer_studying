"""Configuration, read from the environment exactly once.

Two settings groups and one deliberate asymmetry: the **application** connects as a
restricted role, while **migrations** connect as the owner. That split is not decoration.
Row-level security does not apply to a table's owner unless the table is declared
``FORCE ROW LEVEL SECURITY``, so a service that runs its queries as the owner has RLS
switched on and doing nothing. Keeping the two roles in separate settings is what makes
that visible rather than something you discover during an incident.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

#: Service root, overridable so tests can point fixtures at a scratch tree.
PROJECT_ROOT = Path(os.environ.get("SQLGENIE_ROOT", Path(__file__).resolve().parents[2]))

#: Hard ceiling on rows returned to a caller. A text-to-SQL endpoint will eventually be
#: asked a question whose honest answer is the whole table.
MAX_ROWS = 500

#: Statement timeout applied to every generated query, in milliseconds. Generated SQL is
#: not reviewed by anyone before it runs, so an unbounded one is a denial of service
#: waiting for a sufficiently creative question.
STATEMENT_TIMEOUT_MS = 5_000

#: The model name recorded in cassette keys. Changing it invalidates every cassette,
#: which is correct: a different model is a different generator.
MODEL = "claude-sonnet-4-5-20250929"


@dataclass(frozen=True)
class Settings:
    """Everything the service needs to know about where its data and fixtures live.

    Attributes:
        database_url: Connection string for the **application** role. Restricted on
            purpose: it is not the owner of the fact tables.
        migration_url: Connection string for the owner role, used only by migrations.
        root: Service root, from which fixture paths are derived.
        max_rows: Row ceiling for generated queries.
        statement_timeout_ms: Statement timeout for generated queries.
    """

    database_url: str = "postgresql://sqlgenie_app:app@db:5432/sqlgenie"
    migration_url: str = "postgresql://postgres:postgres@db:5432/sqlgenie"
    root: Path = PROJECT_ROOT
    max_rows: int = MAX_ROWS
    statement_timeout_ms: int = STATEMENT_TIMEOUT_MS

    @property
    def cassette_dir(self) -> Path:
        """Directory holding the recorded model responses."""
        return self.root / "fixtures" / "llm_cassettes"

    @property
    def migrations_dir(self) -> Path:
        """Directory holding the numbered SQL migrations."""
        return self.root / "db" / "migrations"

    @property
    def attack_corpus(self) -> Path:
        """The adversarial prompt corpus the security suite is parametrised over."""
        return self.root / "attack" / "prompts.jsonl"


def settings_from_env(**overrides: object) -> Settings:
    """Build settings from the environment, with explicit overrides on top.

    Args:
        **overrides: Field values that win over the environment. Tests use this rather
            than patching ``os.environ``, which keeps the suite order-independent.

    Returns:
        A :class:`Settings`.
    """
    base: dict[str, object] = {
        "database_url": os.environ.get(
            "DATABASE_URL", "postgresql://sqlgenie_app:app@db:5432/sqlgenie"
        ),
        "migration_url": os.environ.get(
            "MIGRATION_DATABASE_URL", "postgresql://postgres:postgres@db:5432/sqlgenie"
        ),
        "root": Path(os.environ.get("SQLGENIE_ROOT", str(PROJECT_ROOT))),
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


#: Process-wide settings. Imported by the API and the CLI; never by ``nl2sql.policy``.
SETTINGS = settings_from_env()
