"""Shared fixtures.

**The fake registry here is not a mock of the real one -- it is the real one, holding
different tools.** That distinction matters: every test below travels the actual
validation, prompt assembly, keying and loop code. Only the handlers are substituted, so
the tests need no database and still prove something about the code that ships.

Cassettes are recorded into a temporary directory by the same function
``tools/gen_cassettes.py`` uses, for the same reason: if the test recorded its fixtures a
second way, the two ways would eventually disagree and the suite would be testing the
disagreement.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pytest

from agentdesk.assistant.recording import Script, ScriptedCall, record
from agentdesk.assistant.registry import Param, Registry, ToolError, ToolSpec
from agentdesk.llm.recorded_client import RecordedClient

#: Pin the clock for every test. SLA state reaches tool output, tool output reaches
#: cassette keys, so an unpinned clock would expire the recordings overnight.
os.environ.setdefault("AGENTDESK_NOW", "2025-06-18T09:00:00+00:00")

TEST_MODEL = "desk-8b-instruct"


def _echo(text: str, times: int = 1) -> str:
    return "echo: " + " ".join([text] * times)


def _fact(topic: str) -> str:
    """A tool whose output is fixed per argument, so keys are reproducible."""
    facts = {
        "probation": "Probation is three months.",
        "refund": "Refunds are issued within 30 days of the invoice date.",
        "vpn": "VPN access needs manager approval and is provisioned at 02:00 UTC.",
    }
    if topic not in facts:
        raise ToolError(f"nothing recorded about {topic!r}")
    return facts[topic]


def _counter(n: int) -> str:
    return f"counted to {n}"


@pytest.fixture
def registry() -> Registry:
    """A registry of deterministic tools, exercising every validation path.

    ``fact`` can fail, ``count`` is typed, ``echo`` has an optional parameter -- between
    them they cover required, optional, enum, coercion and tool failure without touching
    a database.
    """
    return Registry(
        (
            ToolSpec(
                name="echo",
                description="Repeat the text back.",
                parameters=(
                    Param(name="text", type="string", description="What to repeat."),
                    Param(
                        name="times",
                        type="integer",
                        description="How many times. Defaults to once.",
                        required=False,
                    ),
                ),
                handler=_echo,
            ),
            ToolSpec(
                name="fact",
                description="Look up one fact by topic.",
                parameters=(
                    Param(
                        name="topic",
                        type="string",
                        description="Which fact.",
                        enum=("probation", "refund", "vpn"),
                    ),
                ),
                handler=_fact,
            ),
            ToolSpec(
                name="count",
                description="Count to a number.",
                parameters=(
                    Param(name="n", type="integer", description="How high to count."),
                ),
                handler=_counter,
            ),
        )
    )


@pytest.fixture
def cassettes(tmp_path: Path) -> Path:
    """An empty cassette directory for one test."""
    directory = tmp_path / "llm_cassettes"
    directory.mkdir()
    return directory


@pytest.fixture
def recorder(registry: Registry, cassettes: Path):
    """Return a function that records one script and hands back a client.

    Usage::

        client = recorder(Script(id="x", question="...", calls=(...), answer="..."))
    """

    def _record(*scripts: Script, **client_kwargs) -> RecordedClient:
        for script in scripts:
            record(script, registry=registry, model=TEST_MODEL, cassette_dir=cassettes)
        return RecordedClient(cassettes, model=TEST_MODEL, **client_kwargs)

    return _record


@pytest.fixture
def two_step() -> Script:
    """A conversation that needs two tools before it can answer.

    Two rather than one on purpose: a single-step run cannot show whether an observation
    reached the model, because there is no second decision for it to influence.
    """
    return Script(
        id="two-step",
        question="How long do we have to issue a refund, and what did the customer say?",
        calls=(
            ScriptedCall(tool="fact", arguments={"topic": "refund"}, call_id="c0"),
            ScriptedCall(tool="echo", arguments={"text": "we were double charged"}, call_id="c1"),
        ),
        answer="Refunds run 30 days from the invoice date; the customer reports a double charge.",
        citations=("refund",),
        notes="The ordinary two-tool path.",
    )


def ticket_row(
    ticket_id: int = 1,
    *,
    subject: str = "VPN will not connect",
    body: str = "I cannot connect to the VPN since this morning.",
    status: str = "open",
    priority: str = "normal",
    summary: str | None = "Cannot connect to the VPN since this morning.",
) -> tuple:
    """Build one row in :data:`agentdesk.tickets.repository.COLUMNS` order.

    Positional, like the real query, so a column reordered in the repository without
    reordering here shows up as a failure rather than as a quietly wrong field.
    """
    created = datetime(2025, 6, 17, 8, 0, tzinfo=timezone.utc)
    return (
        ticket_id,
        subject,
        body,
        status,
        priority,
        "dana.whitfield@northgate.example",
        None,
        created,
        created,
        summary,
        ["vpn"],
    )


class FakeCursor:
    """Enough of a cursor for the repository tests.

    ``INSERT ... RETURNING id`` gets a synthetic id rather than the configured rows,
    because the one thing every insert here needs back is a primary key.
    """

    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows
        self._last_sql = ""
        self.executed: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None) -> None:
        self._last_sql = sql
        self.executed.append((sql, params))

    def fetchall(self) -> list[tuple]:
        return list(self._rows)

    def fetchone(self) -> tuple | None:
        if self._last_sql.lstrip().upper().startswith("INSERT"):
            return (999,)
        return self._rows[0] if self._rows else None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class FakeConnection:
    """Enough of a connection for the repository tests."""

    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows
        self.commits = 0
        self.cursors: list[FakeCursor] = []

    def cursor(self) -> FakeCursor:
        cursor = FakeCursor(self._rows)
        self.cursors.append(cursor)
        return cursor

    def commit(self) -> None:
        self.commits += 1


class FakePool:
    """A pool that hands out :class:`FakeConnection`.

    Installed through :func:`agentdesk.db.set_pool`, so calls still travel
    :func:`agentdesk.db.connection` and are still instrumented. The probes are the thing
    under test in the latency suite, and a pool that bypassed them would make those tests
    meaningless.
    """

    def __init__(self, rows: list[tuple] | None = None) -> None:
        self.rows = rows or []
        self.checkouts = 0

    @contextmanager
    def connection(self) -> Iterator[FakeConnection]:
        self.checkouts += 1
        yield FakeConnection(self.rows)


@pytest.fixture
def fake_pool() -> Iterator[FakePool]:
    """Install a database-free pool for the duration of one test."""
    from agentdesk import db

    pool = FakePool()
    db.set_pool(pool)
    try:
        yield pool
    finally:
        db.set_pool(None)
