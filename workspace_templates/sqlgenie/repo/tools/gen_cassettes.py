#!/usr/bin/env python3
"""Turn the recording transcript into keyed cassettes.

``fixtures/recordings.jsonl`` is the authored transcript: what was asked, and what came
back. This script derives ``fixtures/llm_cassettes/<key>.json`` from it, where the key is
``sha256(model | system | prompt)`` -- the same key the service computes at request time.

**Both files are committed, and that redundancy is deliberate.** The transcript is
readable and diffable: ``git log -S "WITH" -- fixtures/`` tells you when generated SQL
started using common table expressions, and which commit made it happen. The cassettes
are what the service looks up and are named by a hash nobody can read. Keeping both means
the fixture set can be reviewed by a human and resolved by a machine.

Re-run after any change to the prompt text or the catalog schema, because either moves
every key. ``make cassettes`` does that; ``tests/test_cassettes.py`` fails loudly if you
forget.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlgenie.config import MODEL
from sqlgenie.llm.recorded_client import CASSETTE_VERSION, cassette_key
from sqlgenie.nl2sql import prompt as prompt_module


def load_recordings(path: Path) -> list[dict]:
    """Read the transcript, rejecting duplicate ids.

    Args:
        path: Path to ``recordings.jsonl``.

    Returns:
        The parsed rows, in file order.

    Raises:
        SystemExit: If two rows share an id, which would silently drop one.
    """
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    seen: set[str] = set()
    for row in rows:
        if row["id"] in seen:
            raise SystemExit(f"duplicate recording id {row['id']!r}")
        seen.add(row["id"])
    return rows


def write_cassettes(rows: list[dict], destination: Path, *, prune: bool = True) -> list[Path]:
    """Write one cassette per recording.

    Args:
        rows: Parsed transcript rows.
        destination: Cassette directory.
        prune: Delete cassettes that no recording produces. On by default, because an
            orphan is a response to a question nobody asks any more -- it cannot be
            reached, it cannot be reviewed, and it makes the fixture set look richer
            than it is.

    Returns:
        The paths written.
    """
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    expected: set[str] = set()

    for row in rows:
        rendered = prompt_module.build_prompt(row["question"])
        key = cassette_key(
            model=MODEL, system=prompt_module.SYSTEM_PROMPT, prompt=rendered
        )
        expected.add(key)
        payload = {
            "version": CASSETTE_VERSION,
            "id": row["id"],
            "kind": row["kind"],
            "model": MODEL,
            "question": row["question"],
            "sql": row["sql"],
            "notes": row.get("notes", ""),
        }
        path = destination / f"{key}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)

    if prune:
        for stale in destination.glob("*.json"):
            if stale.stem not in expected:
                stale.unlink()
                print(f"  pruned orphan cassette {stale.name}")

    return written


def main(argv: list[str] | None = None) -> int:
    """Regenerate the cassette set."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--recordings", type=Path, default=Path("fixtures/recordings.jsonl")
    )
    parser.add_argument("--out", type=Path, default=Path("fixtures/llm_cassettes"))
    parser.add_argument("--keep-orphans", action="store_true")
    args = parser.parse_args(argv)

    rows = load_recordings(args.recordings)
    written = write_cassettes(rows, args.out, prune=not args.keep_orphans)
    kinds: dict[str, int] = {}
    for row in rows:
        kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
    summary = ", ".join(f"{count} {kind}" for kind, count in sorted(kinds.items()))
    print(f"wrote {len(written)} cassette(s) to {args.out} ({summary})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
