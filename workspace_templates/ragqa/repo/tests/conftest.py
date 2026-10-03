"""Shared fixtures.

Three kinds of test live here.

**Most need nothing at all.** Chunking, embedding, ranking, routing, guardrails, prompt
assembly and every metric are pure functions over text and ids. Their tests build their
own input as literals and assert constants worked out in the test's own docstring. They
carry no marker and run in milliseconds.

**Some need the corpus and the cassette set**, because what they check is that those two
still agree with the code -- the index fixture is session-scoped since building it is the
same work for every test that wants it.

**A few need Postgres** and are marked ``db``. A missing database makes them fail rather
than skip: a skipped test is green, and these are graded.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from ragqa.config import MODEL, Settings, load_jsonl
from ragqa.llm.recorded_client import RecordedClient
from ragqa.rag.retriever import Index

#: Project root, found from this file rather than the working directory so the suite
#: behaves the same however pytest was invoked.
REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Settings rooted at the repository, so corpus and fixture paths resolve."""
    return Settings(root=REPO_ROOT)


@pytest.fixture(scope="session")
def documents(settings: Settings) -> list[dict]:
    """The authored knowledge base."""
    return load_jsonl(settings.corpus_path)


@pytest.fixture(scope="session")
def index(documents: list[dict]) -> Index:
    """The index as the service builds it."""
    return Index.build(documents)


@pytest.fixture(scope="session")
def client(settings: Settings) -> RecordedClient:
    """A recorded client over the committed cassette set."""
    return RecordedClient(settings.cassette_dir, model=MODEL)


@pytest.fixture(scope="session")
def recordings(settings: Settings) -> list[dict]:
    """The authored recording transcript."""
    return load_jsonl(settings.recordings_path)


@pytest.fixture(scope="session")
def eval_questions(settings: Settings) -> list[dict]:
    """The labelled evaluation set."""
    return load_jsonl(settings.eval_path)


@pytest.fixture
def connection(settings: Settings) -> Iterator:
    """A Postgres connection, rolled back afterwards."""
    import psycopg
    from psycopg.rows import dict_row

    try:
        conn = psycopg.connect(settings.database_url, row_factory=dict_row)
    except psycopg.OperationalError as exc:  # pragma: no cover - environment problem
        raise RuntimeError(
            "PostgreSQL is not reachable at DATABASE_URL. These tests are not skipped "
            "when the database is missing, because a skip is green and would hide a real "
            "failure. Run the suite with `make test`, which runs it inside the container "
            f"where `db` resolves. Original error: {exc}"
        ) from exc
    conn.autocommit = False
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def question_by_id(rows: list[dict], question_id: str) -> dict:
    """Return one row by id, with a useful error when the id is unknown."""
    for row in rows:
        if row["id"] == question_id:
            return row
    raise KeyError(f"no row with id {question_id!r}")
