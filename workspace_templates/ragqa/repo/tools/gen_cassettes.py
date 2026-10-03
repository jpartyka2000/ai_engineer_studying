#!/usr/bin/env python3
"""Turn the recording transcript into keyed cassettes.

``fixtures/recordings.jsonl`` is the authored transcript: what was asked, what came back,
and which passages the model said it used. This derives
``fixtures/llm_cassettes/<key>.json`` from it, where the key is
``sha256(model | system | question)`` -- the same key the service computes at request time.

**Both files are committed, and the redundancy is deliberate.** The transcript is readable
and diffable, so ``git log -S`` over ``fixtures/`` says when an answer changed and which
commit changed it. The cassettes are what the service looks up and are named by a hash
nobody can read. Keeping both means the fixture set can be reviewed by a human and
resolved by a machine.

Re-run after any change to the system prompt, because that moves every key.
``make cassettes`` does it; ``tests/test_cassettes.py`` fails loudly if you forget.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ragqa.config import MODEL, load_jsonl
from ragqa.llm.recorded_client import CASSETTE_VERSION, cassette_key
from ragqa.rag.prompt_builder import SYSTEM_PROMPT


def write_cassettes(rows: list[dict], destination: Path, *, prune: bool = True) -> list[Path]:
    """Write one cassette per recording.

    Args:
        rows: Parsed transcript rows.
        destination: Cassette directory.
        prune: Delete cassettes no recording produces. On by default: an orphan is an
            answer to a question nobody asks, which cannot be reached or reviewed and
            makes the fixture set look richer than it is.

    Returns:
        The paths written.

    Raises:
        SystemExit: On a duplicate recording id, which would silently drop one.
    """
    destination.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    written: list[Path] = []
    expected: set[str] = set()

    for row in rows:
        if row["id"] in seen:
            raise SystemExit(f"duplicate recording id {row['id']!r}")
        seen.add(row["id"])

        key = cassette_key(model=MODEL, system=SYSTEM_PROMPT, question=row["question"])
        expected.add(key)
        payload = {
            "version": CASSETTE_VERSION,
            "id": row["id"],
            "model": MODEL,
            "question": row["question"],
            "answer": row["answer"],
            "citations": list(row.get("citations", [])),
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
    parser.add_argument("--recordings", type=Path, default=Path("fixtures/recordings.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("fixtures/llm_cassettes"))
    parser.add_argument("--keep-orphans", action="store_true")
    args = parser.parse_args(argv)

    rows = load_jsonl(args.recordings)
    written = write_cassettes(rows, args.out, prune=not args.keep_orphans)
    print(f"wrote {len(written)} cassette(s) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
