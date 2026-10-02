"""Command-line entry point.

Everything the service does outside an HTTP request happens here: creating indexes,
loading an export, running the rollup, printing a report. The CLI is thin by design --
each subcommand parses arguments and calls one function from the library -- because a
pipeline step that only exists as a CLI subcommand is a pipeline step that cannot be
unit tested.

``--json`` on every reporting subcommand, so CI can assert on the output instead of
grepping it.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Sequence

from eventstore import analytics, duck, mongo
from eventstore.config import SETTINGS
from eventstore.ingest import group_by_arrival, ingest_events, parse_batch, utcnow
from eventstore.models import to_utc
from eventstore.rollup import run_rollup


def _parse_moment(raw: str) -> datetime:
    """Parse an ISO-8601 timestamp from the command line, rejecting naive values."""
    return to_utc(raw)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(prog="eventstore", description=__doc__.split("\n")[0])
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("indexes", help="create the Mongo indexes if they are missing")

    load = subparsers.add_parser("load", help="load JSONL event exports into Mongo")
    load.add_argument("paths", nargs="+", type=Path, help="one or more .jsonl files")

    rollup = subparsers.add_parser("rollup", help="advance the Mongo -> DuckDB rollup")
    rollup.add_argument(
        "--full", action="store_true", help="reload every event, ignoring the watermark"
    )

    status = subparsers.add_parser("status", help="show counts and the rollup watermark")
    status.add_argument("--service", default=None, help="restrict counts to one service")

    report = subparsers.add_parser("report", help="print a latency and error report")
    report.add_argument("--service", required=True)
    report.add_argument("--route", default=None)
    report.add_argument("--start", type=_parse_moment, default=None)
    report.add_argument("--end", type=_parse_moment, default=None)
    report.add_argument("--minutes", type=int, default=60, help="used when --start is absent")

    return parser


def _emit(payload: dict, as_json: bool) -> None:
    """Print a result, as JSON or as aligned key/value lines."""
    if as_json:
        print(json.dumps(payload, default=str, sort_keys=True))
        return
    width = max((len(key) for key in payload), default=0)
    for key in sorted(payload):
        print(f"{key:<{width}}  {payload[key]}")


def command_indexes(as_json: bool) -> int:
    """Ensure the Mongo indexes exist."""
    client = mongo.get_client()
    try:
        collection = mongo.get_events(mongo.get_database(client))
        names = mongo.ensure_indexes(collection)
    finally:
        client.close()
    _emit({"indexes": names}, as_json)
    return 0


def command_load(paths: Sequence[Path], as_json: bool) -> int:
    """Load JSONL exports into the operational store."""
    client = mongo.get_client()
    totals = {"files": 0, "received": 0, "inserted": 0, "duplicates": 0}
    try:
        collection = mongo.get_events(mongo.get_database(client))
        mongo.ensure_indexes(collection)
        stamp = utcnow()
        for path in paths:
            rows = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if not rows:
                continue
            totals["files"] += 1
            # Replayed as the batches it originally arrived in, oldest first, so the
            # rollup's ingest-time watermark advances the way it did the first time.
            for received_at, batch in group_by_arrival(parse_batch(rows), default_received_at=stamp):
                result = ingest_events(collection, batch, received_at=received_at)
                totals["received"] += result.received
                totals["inserted"] += result.inserted
                totals["duplicates"] += result.duplicates
    finally:
        client.close()
    _emit(totals, as_json)
    return 0


def command_rollup(full: bool, as_json: bool) -> int:
    """Advance the rollup."""
    client = mongo.get_client()
    try:
        collection = mongo.get_events(mongo.get_database(client))
        with duck.warehouse() as connection:
            report = run_rollup(connection, collection, full=full)
    finally:
        client.close()
    _emit(report.as_dict(), as_json)
    return 0


def command_status(service: str | None, as_json: bool) -> int:
    """Show store counts and the rollup watermark."""
    from eventstore.rollup import get_position

    client = mongo.get_client()
    try:
        collection = mongo.get_events(mongo.get_database(client))
        criteria = {"service": service} if service else {}
        payload = {"mongo_events": collection.count_documents(criteria)}
        with duck.warehouse() as connection:
            payload["fact_requests"] = duck.table_count(connection, "fact_requests")
            payload["rollup_minute"] = duck.table_count(connection, "rollup_minute")
            payload["watermark"] = get_position(connection).isoformat()
    finally:
        client.close()
    _emit(payload, as_json)
    return 0


def command_report(
    service: str,
    route: str | None,
    start: datetime | None,
    end: datetime | None,
    minutes: int,
    as_json: bool,
) -> int:
    """Print a latency profile and error rate for a window."""
    window_end = end or utcnow()
    window_start = start or (window_end - timedelta(minutes=minutes))
    with duck.warehouse() as connection:
        errors = analytics.error_rate(
            connection, service=service, start=window_start, end=window_end
        )
        try:
            profile = analytics.latency_profile(
                connection,
                service=service,
                route=route,
                start=window_start,
                end=window_end,
                seed=SETTINGS.bootstrap_seed,
            )
        except ValueError as exc:
            _emit({"service": service, "error": str(exc)}, as_json)
            return 1
    _emit(
        {
            "service": service,
            "route": route or "(all)",
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
            **profile.as_dict(),
            "errors": errors.as_dict(),
        },
        as_json,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Arguments, defaulting to ``sys.argv[1:]``.

    Returns:
        A process exit code.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)

    if args.command == "indexes":
        return command_indexes(args.json)
    if args.command == "load":
        return command_load(args.paths, args.json)
    if args.command == "rollup":
        return command_rollup(args.full, args.json)
    if args.command == "status":
        return command_status(args.service, args.json)
    if args.command == "report":
        return command_report(
            args.service, args.route, args.start, args.end, args.minutes, args.json
        )
    raise AssertionError(f"unhandled command {args.command!r}")  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
