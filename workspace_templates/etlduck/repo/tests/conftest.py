"""Shared fixtures.

Two kinds of test live in this suite and they need different fixtures.

**Unit-level tests build their own tiny landing zone** with ``write_usage`` /
``write_accounts``, so an assertion can name every row that went in. Expectations are
hand-computed and the arithmetic is in the docstring.

**Integration-level tests run against the committed files in ``raw/``**, which were produced
by ``tools/gen_seed_data.py`` with a fixed seed. Those assert exact totals -- 400 silver
rows, 817691 cents -- which is only honest because the generator is deterministic. If a
number here ever has to be "fixed" rather than explained, something regenerated the data
and the right response is to find out why, not to update the constant.

Every fixture gets its own root under ``tmp_path``. DuckDB takes an exclusive lock on the
database file, so sharing one between tests would serialise them at best and deadlock them
at worst.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from etlduck import connect, run_pipeline

#: The project root, found from this file rather than from the working directory so the
#: suite behaves the same however pytest was invoked.
REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """An empty project root with a landing zone."""
    (tmp_path / "raw").mkdir()
    (tmp_path / "warehouse").mkdir()
    return tmp_path


@pytest.fixture
def connection(root: Path):
    """An open warehouse on an empty root. Closed afterwards, because of the file lock."""
    conn = connect(root)
    yield conn
    conn.close()


def write_usage(root: Path, name: str, events: list[dict]) -> Path:
    """Write a usage file into a root's landing zone.

    Args:
        root: The project root.
        name: File name, which must match ``usage_events_*.jsonl`` to be picked up by
            ``ingest_all``.
        events: Records to serialise, one per line.

    Returns:
        The path written.
    """
    path = root / "raw" / name
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    return path


def write_raw_lines(root: Path, name: str, lines: list[str]) -> Path:
    """Write literal lines into the landing zone, for malformed-input tests."""
    path = root / "raw" / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_accounts(root: Path, name: str, rows: list[dict]) -> Path:
    """Write an accounts CSV into a root's landing zone.

    Args:
        root: The project root.
        name: File name, which must match ``accounts*.csv``.
        rows: Dicts with account_id, name, plan, country.

    Returns:
        The path written.
    """
    path = root / "raw" / name
    header = "account_id,name,plan,country"
    body = [f"{r['account_id']},{r['name']},{r['plan']},{r['country']}" for r in rows]
    path.write_text("\n".join([header, *body]) + "\n", encoding="utf-8")
    return path


def event(
    event_id: str,
    account_id: str = "acct-000",
    event_type: str = "api_call",
    occurred_at: str = "2026-03-01T10:00:00+00:00",
    quantity: str = "1",
    amount_cents: str = "100",
) -> dict:
    """Build one well-formed event, overriding only what a test cares about."""
    return {
        "event_id": event_id,
        "account_id": account_id,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "quantity": quantity,
        "amount_cents": amount_cents,
    }


@pytest.fixture
def seeded_root(tmp_path: Path) -> Path:
    """A root holding a copy of the committed landing zone.

    Copied rather than used in place so a test can never write into the repository's own
    ``raw/`` or leave a warehouse file behind in it.
    """
    destination = tmp_path / "seeded"
    (destination / "raw").mkdir(parents=True)
    (destination / "warehouse").mkdir(parents=True)
    for path in sorted((REPO_ROOT / "raw").glob("*")):
        if path.is_file():
            shutil.copy2(path, destination / "raw" / path.name)
    return destination


@pytest.fixture
def seeded(seeded_root: Path):
    """A fully built warehouse over the committed landing zone.

    Yields ``(connection, run_result)``. One pipeline run, so a test asserting on totals and
    a test asserting on the run report are looking at the same build.

    Run with ``strict=False`` deliberately. A fixture that raises takes every test depending
    on it down as an *error* rather than a failure, so one broken quality gate would replace
    a third of this suite's named assertions with the same fixture traceback -- which says
    only that something is wrong, not what. With the gate reported rather than raised, each
    test fails on its own terms and the failing set points at the defect. The gates are
    still asserted, by ``test_every_check_passes_on_clean_data`` and by the checks a run
    returns; nothing is skipped by this, it is only reported differently.
    """
    conn = connect(seeded_root)
    result = run_pipeline(conn, seeded_root, strict=False)
    yield conn, result
    conn.close()
