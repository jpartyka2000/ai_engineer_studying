#!/usr/bin/env python
"""Measure how much work scoring does.

Reports **operation counts** alongside timings, and the counts are what should be held
to a threshold. Wall-clock on a laptop under Docker varies by a factor of several
depending on what else is running; the number of artifact loads and feature-pipeline
invocations per request does not.

Prints a single JSON object on the last line, which is the contract the grading harness
reads.

    python bench/bench_predict.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from svc.features import pipeline as pipeline_module  # noqa: E402
from svc.model import registry as registry_module  # noqa: E402
from svc.schemas import PredictRequest  # noqa: E402

BATCH_SIZE = 200


def sample_accounts(count: int) -> list[PredictRequest]:
    """Build a deterministic batch of scoring requests."""
    return [
        PredictRequest(
            account_id=f"bench-{index:04d}",
            plan=("free", "team", "enterprise")[index % 3],
            seats=1 + (index % 300),
            monthly_spend=float((index % 40) * 250),
            tenure_days=30 + (index % 900),
            support_tickets=index % 6,
            has_sso=bool(index % 2),
        )
        for index in range(count)
    ]


class Counter:
    """Wraps a function to count how often it is called."""

    def __init__(self, target):
        self.target = target
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self.target(*args, **kwargs)


def measure(count: int) -> dict:
    """Score a batch and report the work done."""
    from svc.routers.predict import _score_one

    accounts = sample_accounts(count)

    # Count artifact loads and pipeline invocations rather than timing them. One load
    # for the whole batch is correct; one per request means the cache is being defeated.
    load_counter = Counter(registry_module.get_loaded_model)
    build_counter = Counter(pipeline_module.build_features)
    original_load = registry_module.get_loaded_model
    original_build = pipeline_module.build_features

    import svc.routers.predict as predict_module

    predict_module.get_loaded_model = load_counter
    predict_module.build_features = build_counter
    try:
        loaded = original_load()
        started = time.perf_counter()
        for account in accounts:
            _score_one(loaded, account)
        elapsed_ms = (time.perf_counter() - started) * 1000
    finally:
        predict_module.get_loaded_model = original_load
        predict_module.build_features = original_build

    return {
        "requests": count,
        "artifact_loads": load_counter.calls,
        "feature_builds": build_counter.calls,
        "feature_builds_per_request": round(build_counter.calls / count, 4),
        "elapsed_ms": round(elapsed_ms, 2),
        "us_per_request": round(elapsed_ms * 1000 / count, 2),
    }


def main() -> None:
    """Run the benchmark."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=BATCH_SIZE)
    parser.add_argument("--json", action="store_true", help="Print JSON only.")
    args = parser.parse_args()

    result = measure(args.count)
    if not args.json:
        print(f"requests scored           : {result['requests']}")
        print(f"artifact loads            : {result['artifact_loads']}  (should be 1)")
        print(f"feature builds per request: {result['feature_builds_per_request']}  (should be 1)")
        print(f"wall clock                : {result['elapsed_ms']} ms "
              f"({result['us_per_request']} us/request)")
        print()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
