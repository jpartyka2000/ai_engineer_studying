"""Command-line interface.

    edakit profile datasets/customers.csv
    edakit profile datasets/customers.csv --format markdown
    edakit missing datasets/customers.csv --threshold 0.3
"""

from __future__ import annotations

import argparse
import sys

from edakit.missing import analyse_missing
from edakit.profile import load_csv, profile_dataset
from edakit.report import render_markdown, render_text


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(prog="edakit", description="Explore a tabular dataset.")
    sub = parser.add_subparsers(dest="command", required=True)

    profile_cmd = sub.add_parser("profile", help="Profile a CSV file.")
    profile_cmd.add_argument("path", help="Path to the CSV.")
    profile_cmd.add_argument(
        "--format", choices=("text", "markdown"), default="text", help="Output format."
    )
    profile_cmd.add_argument("--delimiter", default=",", help="Field delimiter.")

    missing_cmd = sub.add_parser("missing", help="Report missing values.")
    missing_cmd.add_argument("path", help="Path to the CSV.")
    missing_cmd.add_argument(
        "--threshold", type=float, default=0.0, help="Only show columns at or above this fraction."
    )
    missing_cmd.add_argument("--delimiter", default=",", help="Field delimiter.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Arguments, defaulting to ``sys.argv[1:]``.

    Returns:
        A process exit code. 1 on a bad path or malformed file, so a shell script
        calling this can branch on it.
    """
    args = build_parser().parse_args(argv)

    try:
        rows, columns = load_csv(args.path, delimiter=args.delimiter)
    except (FileNotFoundError, ValueError) as exc:
        print(f"edakit: {exc}", file=sys.stderr)
        return 1

    if args.command == "profile":
        profile = profile_dataset(rows, columns)
        renderer = render_markdown if args.format == "markdown" else render_text
        print(renderer(profile), end="")
        return 0

    report = analyse_missing(rows)
    print(f"rows: {report.total_rows}  complete: {report.complete_rows} "
          f"({report.completeness:.0%})")
    for name, fraction in sorted(report.null_fractions.items(), key=lambda kv: -kv[1]):
        if fraction >= args.threshold:
            print(f"  {name:24} {fraction:>6.1%}  ({report.null_counts[name]} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
