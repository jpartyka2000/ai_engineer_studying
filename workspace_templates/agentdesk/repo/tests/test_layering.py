"""The import directions this codebase depends on.

An architectural rule that nothing checks is a comment. These are the three that have
actually been broken here, each by somebody doing something reasonable.

The checks read source rather than imported modules on purpose: an import inside a
function body is still an import, still couples the two packages, and is exactly the form
a rule like this gets broken in -- because it looks local and temporary.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "agentdesk"


def imported_modules(path: Path) -> set[str]:
    """Return every module name imported by a file, including inside functions."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def files_in(package: str) -> list[Path]:
    return sorted((SRC / package).rglob("*.py"))


@pytest.mark.parametrize("path", files_in("tickets"), ids=lambda p: p.name)
def test_the_desk_does_not_import_the_assistant(path: Path) -> None:
    """**The rule the whole latency story rests on.**

    The desk predates the assistant by three years and has to keep serving when the
    assistant is down. That is only true if it cannot reach it: one import is enough to
    turn a model outage into a ticket-list outage.
    """
    offending = {
        name for name in imported_modules(path) if name.startswith("agentdesk.assistant")
    }
    assert not offending, f"{path.name} imports {sorted(offending)}"


@pytest.mark.parametrize("path", files_in("tickets"), ids=lambda p: p.name)
def test_the_desk_does_not_import_the_serving_layer(path: Path) -> None:
    """The desk does not care where the model runs, or that one exists."""
    offending = {
        name for name in imported_modules(path) if name.startswith("agentdesk.serving")
    }
    assert not offending, f"{path.name} imports {sorted(offending)}"


@pytest.mark.parametrize("path", files_in("serving"), ids=lambda p: p.name)
def test_the_serving_layer_stands_alone(path: Path) -> None:
    """It is arithmetic. It must not reach the database, the desk or the assistant.

    Keeping it free-standing is what lets a capacity question be answered in a REPL, and
    what keeps its tests exact.
    """
    forbidden = ("agentdesk.tickets", "agentdesk.assistant", "agentdesk.db", "psycopg")
    offending = {
        name
        for name in imported_modules(path)
        if any(name.startswith(prefix) for prefix in forbidden)
    }
    assert not offending, f"{path.name} imports {sorted(offending)}"


@pytest.mark.parametrize("path", files_in("serving"), ids=lambda p: p.name)
def test_the_serving_layer_does_not_import_a_tensor_library(path: Path) -> None:
    """There is no accelerator here and no inference. This module plans; it does not run.

    Stated as a test because the temptation to "just import torch for the dtype sizes" is
    real, and it would make the exercise unrunnable on every machine it is sat on.
    """
    offending = {
        name
        for name in imported_modules(path)
        if name.split(".")[0] in {"torch", "jax", "tensorflow", "numpy"}
    }
    assert not offending, f"{path.name} imports {sorted(offending)}"


def test_every_database_access_goes_through_the_pool_helper() -> None:
    """``agentdesk.db.connection`` is the only sanctioned checkout.

    The probe that answers "was a connection held across a model call?" can only see
    checkouts it was told about. A module calling ``psycopg.connect`` directly is
    invisible to it, and the rule silently stops applying to that module.
    """
    offenders = []
    for path in SRC.rglob("*.py"):
        if path.name == "db.py":
            continue
        source = path.read_text(encoding="utf-8")
        if "psycopg.connect" in source or "ConnectionPool(" in source:
            offenders.append(path.relative_to(SRC).as_posix())
    assert offenders == [], f"{offenders} open connections outside agentdesk.db"
