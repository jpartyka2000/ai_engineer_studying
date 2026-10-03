"""Configuration, read from the environment exactly once.

Nothing here reads the environment at import time except :data:`SETTINGS`, and a test
that needs different settings constructs its own :class:`Settings` rather than mutating
``os.environ`` -- which is what keeps the suite parallelisable and order-independent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

#: Service root, overridable so tests can point fixtures at a scratch tree.
PROJECT_ROOT = Path(os.environ.get("RAGQA_ROOT", Path(__file__).resolve().parents[2]))

#: The model name recorded in cassette keys. Changing it invalidates every cassette,
#: which is correct: a different model is a different generator.
MODEL = "claude-sonnet-4-5-20250929"


@dataclass(frozen=True)
class Settings:
    """Where the corpus, fixtures and database live.

    Attributes:
        database_url: Connection string for conversation storage.
        root: Service root, from which fixture paths derive.
    """

    database_url: str = "postgresql://ragqa:ragqa@db:5432/ragqa"
    root: Path = PROJECT_ROOT

    @property
    def corpus_path(self) -> Path:
        """The authored knowledge base."""
        return self.root / "corpus" / "documents.jsonl"

    @property
    def cassette_dir(self) -> Path:
        """Recorded model responses."""
        return self.root / "fixtures" / "llm_cassettes"

    @property
    def recordings_path(self) -> Path:
        """The readable transcript the cassettes derive from."""
        return self.root / "fixtures" / "recordings.jsonl"

    @property
    def eval_path(self) -> Path:
        """The labelled evaluation set."""
        return self.root / "eval" / "questions.jsonl"


def settings_from_env(**overrides: object) -> Settings:
    """Build settings from the environment, with explicit overrides on top."""
    base: dict[str, object] = {
        "database_url": os.environ.get(
            "DATABASE_URL", "postgresql://ragqa:ragqa@db:5432/ragqa"
        ),
        "root": Path(os.environ.get("RAGQA_ROOT", str(PROJECT_ROOT))),
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def load_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file into a list of dicts, skipping blank lines."""
    import json

    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


#: Process-wide settings. Imported by the API and the CLI; never by ``rag`` or ``eval``.
SETTINGS = settings_from_env()
