"""Command-line entry point.

Everything the service does outside an HTTP request: apply migrations, ask one question,
inspect the index, and run the evaluation set. Thin by design -- each subcommand parses
arguments and calls one library function -- because a step that exists only as a CLI
subcommand is a step that cannot be unit tested.

``--json`` on every reporting subcommand, so CI asserts on output rather than grepping it.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Sequence

from ragqa.config import MODEL, SETTINGS, load_jsonl
from ragqa.eval.runner import evaluate
from ragqa.llm.recorded_client import RecordedClient
from ragqa.rag.pipeline import answer_question
from ragqa.rag.retriever import Index


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(prog="ragqa", description=__doc__.split("\n")[0])
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("migrate", help="apply pending SQL migrations")
    subparsers.add_parser("index", help="build the index and report its shape")

    ask = subparsers.add_parser("ask", help="answer one question")
    ask.add_argument("question")
    ask.add_argument("--top-k", type=int, default=None)

    run_eval = subparsers.add_parser("eval", help="run the labelled evaluation set")
    run_eval.add_argument("--top-k", type=int, default=None)
    run_eval.add_argument(
        "--detail", action="store_true", help="list every question's scores"
    )

    return parser


def _emit(payload: dict, as_json: bool) -> None:
    """Print a result, as JSON or as aligned key/value lines."""
    if as_json:
        print(json.dumps(payload, default=str, sort_keys=True))
        return
    width = max((len(key) for key in payload), default=0)
    for key in sorted(payload):
        print(f"{key:<{width}}  {payload[key]}")


def _index() -> Index:
    """Build the index from the configured corpus."""
    return Index.build(load_jsonl(SETTINGS.corpus_path))


def _client() -> RecordedClient:
    """Open the recorded client over the configured cassette set."""
    return RecordedClient(SETTINGS.cassette_dir, model=MODEL)


def command_migrate(as_json: bool) -> int:
    """Apply pending migrations."""
    from ragqa import db

    applied = db.migrate()
    _emit({"applied": applied, "count": len(applied)}, as_json)
    return 0


def command_index(as_json: bool) -> int:
    """Report the index's shape."""
    index = _index()
    lengths = sorted(len(c.text) for c in index.chunks)
    _emit(
        {
            "documents": len({c.doc_id for c in index.chunks}),
            "chunks": len(index),
            "vocabulary": len(index.vectorizer.idf),
            "dimensions": index.vectorizer.dimensions,
            "chunk_chars_min": lengths[0],
            "chunk_chars_max": lengths[-1],
        },
        as_json,
    )
    return 0


def command_ask(question: str, top_k: int | None, as_json: bool) -> int:
    """Answer one question."""
    kwargs = {"top_k": top_k} if top_k else {}
    answer = answer_question(question, index=_index(), client=_client(), **kwargs)
    _emit(answer.as_dict(), as_json)
    return 0


def command_eval(top_k: int | None, detail: bool, as_json: bool) -> int:
    """Run the evaluation set.

    Returns:
        0 always. The exit code is not a pass/fail gate -- thresholds are the grading
        harness's business, and a CLI that failed on a metric regression would make
        every experiment look like a broken build.
    """
    kwargs = {"top_k": top_k} if top_k else {}
    report = evaluate(load_jsonl(SETTINGS.eval_path), index=_index(), client=_client(), **kwargs)

    if detail and not as_json:
        for result in report.results:
            flag = "REFUSED" if result.refused else "       "
            print(
                f"  {result.id:4s} {flag} em={result.exact_match:.2f} f1={result.token_f1:.2f} "
                f"citP={result.citation_precision:.2f} {result.question[:46]}"
            )
        print()

    _emit(report.as_dict(), as_json)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)

    if args.command == "migrate":
        return command_migrate(args.json)
    if args.command == "index":
        return command_index(args.json)
    if args.command == "ask":
        return command_ask(args.question, args.top_k, args.json)
    if args.command == "eval":
        return command_eval(args.top_k, args.detail, args.json)
    raise AssertionError(f"unhandled command {args.command!r}")  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
