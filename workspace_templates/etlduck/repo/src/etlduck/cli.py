"""Command line entry point.

    etlduck run                 bronze, silver, gold, quality, watermark
    etlduck bronze              ingest the landing zone only
    etlduck silver              rebuild silver from bronze
    etlduck gold                rebuild gold from silver
    etlduck check               run the quality gates and report
    etlduck profile raw/        describe the landing-zone files
    etlduck watermark           show the current watermark

Every subcommand exits non-zero when the thing it did failed, because these are run from a
job scheduler that only looks at the exit code.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from etlduck import quality
from etlduck.bronze import ingest_all
from etlduck.config import paths
from etlduck.db import warehouse
from etlduck.gold import build_gold
from etlduck.pipeline import USAGE_STREAM, run_pipeline
from etlduck.profile import profile_landing_zone, render_profiles
from etlduck.silver import build_silver
from etlduck.watermark import get_watermark


def _add_root(parser: argparse.ArgumentParser) -> None:
    """Every subcommand takes a root override, so tests can drive the CLI."""
    parser.add_argument("--root", default=None, help="Project root (default: the package's)")


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    parser = argparse.ArgumentParser(prog="etlduck", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("run", "Run the whole pipeline"),
        ("bronze", "Ingest the landing zone"),
        ("silver", "Rebuild silver from bronze"),
        ("gold", "Rebuild gold from silver"),
        ("check", "Run the quality gates"),
        ("watermark", "Show the current watermark"),
    ):
        command = sub.add_parser(name, help=help_text)
        _add_root(command)
        if name in {"run", "check"}:
            command.add_argument("--json", action="store_true", help="Machine-readable output")
        if name == "run":
            command.add_argument(
                "--no-strict",
                action="store_true",
                help="Report failing checks instead of exiting non-zero",
            )

    profile = sub.add_parser("profile", help="Describe the landing-zone files")
    _add_root(profile)
    profile.add_argument("directory", nargs="?", default=None, help="Directory to profile")
    profile.add_argument("--pattern", default="*.jsonl")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Returns:
        0 on success; 1 when a quality gate failed or a file was missing.
    """
    args = build_parser().parse_args(argv)

    if args.command == "profile":
        directory = Path(args.directory) if args.directory else paths(args.root).raw
        try:
            profiles = profile_landing_zone(directory, args.pattern)
        except FileNotFoundError as exc:
            print(f"etlduck: {exc}", file=sys.stderr)
            return 1
        print(render_profiles(profiles))
        return 0

    with warehouse(args.root) as connection:
        if args.command == "bronze":
            for load in ingest_all(connection, args.root):
                state = "skipped (already loaded)" if load.skipped_as_duplicate else "loaded"
                print(f"{load.source_file}: {state}, {load.rows_inserted} rows")
            return 0

        if args.command == "silver":
            result = build_silver(connection)
            print(
                f"silver: {result.rows_written} rows, {result.rows_quarantined} quarantined, "
                f"{result.duplicates_collapsed} duplicates collapsed"
            )
            return 0

        if args.command == "gold":
            result = build_gold(connection)
            print(
                f"gold: {result.rows_written} rows over {result.distinct_dates} dates, "
                f"{result.total_amount_cents} cents"
            )
            return 0

        if args.command == "watermark":
            print(f"{USAGE_STREAM}: {get_watermark(connection, USAGE_STREAM).isoformat()}")
            return 0

        if args.command == "check":
            checks = quality.run_all(connection)
            if args.json:
                print(
                    json.dumps(
                        {
                            "passed": all(c.passed for c in checks),
                            "checks": [
                                {"name": c.name, "passed": c.passed, "detail": c.detail}
                                for c in checks
                            ],
                        }
                    )
                )
            else:
                for check in checks:
                    print(check)
            return 0 if all(check.passed for check in checks) else 1

        # run
        try:
            result = run_pipeline(connection, args.root, strict=not args.no_strict)
        except quality.QualityFailure as exc:
            print(f"etlduck: quality gate failed: {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(
                json.dumps(
                    {
                        "files_loaded": result.files_loaded,
                        "files_skipped": result.files_skipped,
                        "silver_rows": result.silver.rows_written if result.silver else 0,
                        "quarantined": result.silver.rows_quarantined if result.silver else 0,
                        "duplicates_collapsed": (
                            result.silver.duplicates_collapsed if result.silver else 0
                        ),
                        "gold_rows": result.gold.rows_written if result.gold else 0,
                        "total_amount_cents": (
                            result.gold.total_amount_cents if result.gold else 0
                        ),
                        "checks_passed": result.ok,
                    }
                )
            )
        else:
            print(result.summary())
        return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
