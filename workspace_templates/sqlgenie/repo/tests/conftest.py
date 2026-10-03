"""Shared fixtures.

Three kinds of test live in this suite.

**Policy tests need nothing.** The tenant rewrite is a pure function from SQL text to SQL
text, so its tests pass literals and assert on the result. They are the majority, they
run in milliseconds, and they carry no marker.

**Cassette tests need the fixture set** and the live prompt-assembly code, because what
they check is that the two still agree.

**Database tests need Postgres** and are marked ``db``. Each runs inside a transaction
that is rolled back, against a database seeded with two tenants whose data overlaps on
every natural key -- same customer names, same SKUs, same order ids. That overlap is
deliberate: an isolation bug that returns the wrong tenant's rows is invisible if the
two tenants' data is distinguishable by content.

A missing Postgres **raises rather than skips**. A skipped security test is a green
security test, and these are graded.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest

from sqlgenie.config import MODEL, Settings
from sqlgenie.llm.recorded_client import RecordedClient

#: Project root, found from this file rather than the working directory so the suite
#: behaves the same however pytest was invoked.
REPO_ROOT = Path(__file__).resolve().parents[1]

#: The two seeded tenants. ACME is "us" in every test; BORG is the tenant whose rows
#: must never appear.
TENANT_A = "acme"
TENANT_B = "borg"


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Settings rooted at the repository, so fixture paths resolve."""
    return Settings(root=REPO_ROOT)


@pytest.fixture(scope="session")
def recordings() -> list[dict]:
    """The authored recording transcript, in file order."""
    path = REPO_ROOT / "fixtures" / "recordings.jsonl"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.fixture(scope="session")
def attack_cases() -> list[dict]:
    """The adversarial corpus with its declared expectations."""
    path = REPO_ROOT / "attack" / "prompts.jsonl"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.fixture(scope="session")
def client(settings: Settings) -> RecordedClient:
    """A recorded client over the committed cassette set."""
    return RecordedClient(settings.cassette_dir, model=MODEL)


@pytest.fixture
def connection(settings: Settings) -> Iterator["psycopg.Connection"]:  # noqa: F821
    """A connection in a transaction that is rolled back afterwards.

    Rolled back rather than truncated, so a test that writes cannot leak into the next
    one and the seeded fixture never has to be rebuilt mid-suite.

    psycopg is imported here rather than at module scope on purpose: the policy and
    cassette tests are pure and must stay runnable without a database driver installed,
    which is also what lets CI assert that they are.
    """
    import psycopg
    from psycopg.rows import dict_row

    try:
        conn = psycopg.connect(settings.database_url, row_factory=dict_row)
    except psycopg.OperationalError as exc:  # pragma: no cover - environment problem
        raise RuntimeError(
            "PostgreSQL is not reachable at DATABASE_URL. These tests are not skipped "
            "when the database is missing, because a skipped security test is a green "
            "security test. Run the suite with `make test`, which runs it inside the "
            f"container where `db` resolves. Original error: {exc}"
        ) from exc
    conn.autocommit = False
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture
def ask_as(connection, client: RecordedClient, settings: Settings):
    """Answer a question as a tenant, through the real pipeline.

    Runs inside the same rolled-back transaction as ``connection``, so an end-to-end
    test leaves nothing behind. Returns the ``Answer`` rather than a dict, because the
    security tests assert on the rewrite report as well as on the rows.
    """
    from sqlgenie.nl2sql import pipeline
    from sqlgenie.tenancy import context

    def _ask(tenant_id: str, question: str):
        with context.bind_tenant(tenant_id):
            return pipeline.ask(
                question,
                connection=connection,
                client=client,
                tenant_id=tenant_id,
                max_rows=settings.max_rows,
                statement_timeout_ms=settings.statement_timeout_ms,
            )

    return _ask


def recording_by_id(recordings: list[dict], recording_id: str) -> dict:
    """Return one recording, with a useful error when the id is unknown."""
    for row in recordings:
        if row["id"] == recording_id:
            return row
    raise KeyError(f"no recording with id {recording_id!r}")
