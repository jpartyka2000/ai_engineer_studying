#!/usr/bin/env python
"""Evaluate the current model against the held-out labelled set.

Prints a single JSON object on the last line, which is the contract the grading harness
reads:

    python eval/run_eval.py --json
    python eval/run_eval.py --assert-f1 0.55
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.metrics import confusion_matrix  # noqa: E402
from svc.features.pipeline import FeatureError, build_features  # noqa: E402
from svc.model.registry import ArtifactError, get_loaded_model  # noqa: E402
from svc.model.scorer import MissingFeature, predict  # noqa: E402

DEFAULT_DATASET = Path(__file__).resolve().parent.parent / "data" / "eval_labeled.csv"
LABEL_COLUMN = "churned"


def load_rows(path: Path) -> list[dict[str, str]]:
    """Read the labelled evaluation set.

    Raises:
        FileNotFoundError: If the file is absent.
        ValueError: If the label column is missing.
    """
    if not path.is_file():
        raise FileNotFoundError(f"evaluation set not found: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if rows and LABEL_COLUMN not in rows[0]:
        raise ValueError(f"{path} has no {LABEL_COLUMN!r} column")
    return rows


def evaluate(rows: list[dict[str, str]]) -> dict:
    """Score every row and summarise.

    Rows the feature pipeline rejects are counted separately rather than being dropped
    silently or scored as negatives: a model that cannot produce a prediction has not
    got that row right, and hiding those rows would inflate every metric.

    Args:
        rows: The labelled set.

    Returns:
        A dict of metrics plus ``skipped`` and model identity.
    """
    loaded = get_loaded_model()
    actual: list[int] = []
    predicted: list[int] = []
    skipped = 0

    for row in rows:
        try:
            features = build_features(loaded.spec, dict(row))
            label, _probability = predict(loaded.model, features)
        except (FeatureError, MissingFeature):
            skipped += 1
            continue
        actual.append(int(row[LABEL_COLUMN]))
        predicted.append(label)

    matrix = confusion_matrix(actual, predicted)
    return {
        "model": loaded.identifier,
        "feature_spec": loaded.spec.version,
        "rows": len(rows),
        "scored": len(actual),
        "skipped": skipped,
        **matrix.as_dict(),
    }


def main(argv: list[str] | None = None) -> int:
    """Run the evaluation.

    Returns:
        0 on success, 1 if an assertion threshold was not met or an artifact is bad.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--json", action="store_true", help="Print JSON only.")
    parser.add_argument("--assert-f1", type=float, default=None, help="Fail below this F1.")
    parser.add_argument(
        "--assert-accuracy", type=float, default=None, help="Fail below this accuracy."
    )
    args = parser.parse_args(argv)

    try:
        rows = load_rows(args.dataset)
        result = evaluate(rows)
    except (ArtifactError, FileNotFoundError, ValueError) as exc:
        print(f"run_eval: {exc}", file=sys.stderr)
        return 1

    if not args.json:
        print(f"model            : {result['model']} (spec {result['feature_spec']})")
        print(f"rows / scored    : {result['rows']} / {result['scored']}"
              f"{f'  ({result['skipped']} skipped)' if result['skipped'] else ''}")
        print(f"positive rate    : {result['positive_rate']:.1%}")
        print()
        print(f"F1               : {result['f1']:.4f}   <- primary metric")
        print(f"precision        : {result['precision']:.4f}")
        print(f"recall           : {result['recall']:.4f}")
        print(f"accuracy         : {result['accuracy']:.4f}")
        print(f"  majority baseline: {result['majority_baseline_accuracy']:.4f}"
              "   <- beat this, not zero")
        print()
        print(f"confusion        : tp={result['true_positive']} fp={result['false_positive']} "
              f"tn={result['true_negative']} fn={result['false_negative']}")
        print()

    failed = False
    if args.assert_f1 is not None and result["f1"] < args.assert_f1:
        print(f"FAIL: F1 {result['f1']:.4f} is below the required {args.assert_f1}", file=sys.stderr)
        failed = True
    if args.assert_accuracy is not None and result["accuracy"] < args.assert_accuracy:
        print(
            f"FAIL: accuracy {result['accuracy']:.4f} is below the required "
            f"{args.assert_accuracy}",
            file=sys.stderr,
        )
        failed = True

    print(json.dumps(result))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
