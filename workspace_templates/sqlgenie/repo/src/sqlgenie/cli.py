"""Command-line entry point.

Everything the service does outside an HTTP request: migrate, seed, ask a question, and
replay the adversarial corpus. Thin by design -- each subcommand parses arguments and
calls one library function -- because a step that exists only as a CLI subcommand is a
step that cannot be unit tested.

``--json`` on every reporting subcommand, so CI asserts on output instead of grepping it.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Sequence

from sqlgenie.config import MODEL, SETTINGS
from sqlgenie.db import migrate, pool
from sqlgenie.llm.recorded_client import RecordedClient
from sqlgenie.nl2sql import pipeline
from sqlgenie.nl2sql.executor import ExecutionError
from sqlgenie.nl2sql.pipeline import RefusedError
from sqlgenie.nl2sql.policy.row_level_policy import PolicyError, enforce_tenant_scope
from sqlgenie.tenancy import context


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(prog="sqlgenie", description=__doc__.split("\n")[0])
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("migrate", help="apply pending SQL migrations")

    seed = subparsers.add_parser("seed", help="load the two-tenant development data")
    seed.add_argument("--file", type=Path, default=Path("db/seed.sql"))

    ask = subparsers.add_parser("ask", help="answer one question as a tenant")
    ask.add_argument("question")
    ask.add_argument("--tenant", required=True, help="tenant id to answer as")

    replay = subparsers.add_parser(
        "replay", help="run the adversarial corpus through the policy"
    )
    replay.add_argument("--corpus", type=Path, default=Path("attack/prompts.jsonl"))
    replay.add_argument("--recordings", type=Path, default=Path("fixtures/recordings.jsonl"))

    return parser


def _emit(payload: dict, as_json: bool) -> None:
    """Print a result, as JSON or as aligned key/value lines."""
    if as_json:
        print(json.dumps(payload, default=str, sort_keys=True))
        return
    width = max((len(key) for key in payload), default=0)
    for key in sorted(payload):
        print(f"{key:<{width}}  {payload[key]}")


def command_migrate(as_json: bool) -> int:
    """Apply pending migrations."""
    applied = migrate.apply_all()
    _emit({"applied": applied, "count": len(applied)}, as_json)
    return 0


def command_seed(path: Path, as_json: bool) -> int:
    """Load the development data."""
    sql = path.read_text(encoding="utf-8")
    with pool.owner_connection() as connection, connection.cursor() as cursor:
        cursor.execute(sql)
    _emit({"seeded_from": str(path)}, as_json)
    return 0


def command_ask(question: str, tenant: str, as_json: bool) -> int:
    """Answer one question as a tenant."""
    client = RecordedClient(SETTINGS.cassette_dir, model=MODEL)
    with context.bind_tenant(tenant):
        try:
            with pool.app_connection() as connection:
                answer = pipeline.ask(
                    question,
                    connection=connection,
                    client=client,
                    tenant_id=tenant,
                    max_rows=SETTINGS.max_rows,
                    statement_timeout_ms=SETTINGS.statement_timeout_ms,
                )
        except RefusedError as exc:
            _emit({"question": question, "outcome": "refused", "reason": str(exc)}, as_json)
            return 1
        except ExecutionError as exc:
            _emit({"question": question, "outcome": "failed", "reason": str(exc)}, as_json)
            return 1
    _emit(answer.as_dict(), as_json)
    return 0


def command_replay(corpus: Path, recordings: Path, as_json: bool) -> int:
    """Run every adversarial case through the policy and report mismatches.

    Exits non-zero if any case does something other than what the corpus declares. This
    is the check CI runs; it needs no database, because what it is testing is the
    rewrite rather than the result.
    """
    cases = [json.loads(line) for line in corpus.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_id = {
        row["id"]: row
        for row in (
            json.loads(line)
            for line in recordings.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }

    mismatches: list[dict] = []
    for case in cases:
        row = by_id.get(case["id"])
        if row is None:
            mismatches.append({"id": case["id"], "expected": case["expect"], "actual": "missing"})
            continue
        try:
            result = enforce_tenant_scope(row["sql"])
        except PolicyError:
            actual = "refused"
        else:
            actual = "scoped" if result.predicates_added else "allowed"
        if actual != case["expect"]:
            mismatches.append(
                {"id": case["id"], "probes": case["probes"], "expected": case["expect"], "actual": actual}
            )

    _emit({"cases": len(cases), "mismatches": mismatches, "ok": not mismatches}, as_json)
    return 1 if mismatches else 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)

    if args.command == "migrate":
        return command_migrate(args.json)
    if args.command == "seed":
        return command_seed(args.file, args.json)
    if args.command == "ask":
        return command_ask(args.question, args.tenant, args.json)
    if args.command == "replay":
        return command_replay(args.corpus, args.recordings, args.json)
    raise AssertionError(f"unhandled command {args.command!r}")  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
