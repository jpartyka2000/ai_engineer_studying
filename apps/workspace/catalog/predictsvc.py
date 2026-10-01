"""Exercises built on the ``predictsvc`` base application.

Same ``(base_app, mutations)`` shape as :mod:`apps.workspace.catalog.tenantsaas`, and
baselines are likewise **measured** into ``baselines.json`` by the verification harness
rather than authored here.

What makes this base app different from ``tenantsaas`` is where its defects live. A
scoring service can be completely correct as code and still serve wrong numbers, because
half its behaviour is in ``artifacts/``. The exercises here are mostly about that seam.
"""

import json
from pathlib import Path
from typing import Any

from apps.workspace.enums import BaseApp, CheckKind, Difficulty, ExerciseType

_BASELINES: dict[str, dict[str, Any]] = json.loads(
    (Path(__file__).parent / "baselines.json").read_text(encoding="utf-8")
)


def baseline(slug: str) -> dict[str, Any]:
    """Return the measured pre-fix baseline for an exercise.

    Args:
        slug: The exercise slug.

    Returns:
        A dict with ``failing_nodes``, ``passing_nodes`` and ``metrics``.

    Raises:
        KeyError: If no baseline has been measured, which should fail the seed
            command rather than silently ship an ungradeable exercise.
    """
    data = _BASELINES[slug]
    return {
        "failing_nodes": data["failing_nodes"],
        "passing_nodes": data["passing_nodes"],
        "metrics": data.get("metrics", {}),
    }


#: The tests are the proof, so editing them is tampering. ``artifacts/archive/**`` joins
#: them here because it is the audit record of what each spec version meant: a candidate
#: who edits an archived spec to agree with a broken active one has destroyed the only
#: evidence of the defect rather than fixed it. ``model_v3.json`` is protected because
#: this repository serves models and does not train them -- compensating for a bad
#: feature contract by moving the coefficients is not a fix available here.
STANDARD_PROTECTED = [
    "tests/**",
    "pytest.ini",
    "ci/run_ci.sh",
    "artifacts/model_v3.json",
    "artifacts/archive/**",
]

#: For exercises whose wrong turn is "retune the artifact instead of fixing the code".
#: Freezing all of ``artifacts/`` makes that tampering rather than a defensible
#: alternative, and matches those briefs, which say the artifacts are off limits.
ARTIFACTS_FROZEN = [
    "tests/**",
    "pytest.ini",
    "ci/run_ci.sh",
    "artifacts/**",
]

#: Shared context: the paragraph stating what the registry's compatibility checks do
#: *not* cover, which is the rule any fix at this seam has to be judged against.
SKEW_EXCERPT = {
    "path": "ARCHITECTURE.md",
    "line_range": "22-52",
    "why": (
        "States the train/serve-skew rules, including the explicit note that "
        "assert_compatible compares names only and cannot see an edited feature value."
    ),
}


# ---------------------------------------------------------------------------
# ex-009 -- implement and deploy an ML model
# ---------------------------------------------------------------------------

EX009 = {
    "slug": "ex-009-churn-scores-skewed-after-deploy",
    "exercise_number": 9,
    "title": "Churn scores went wrong after Tuesday's deploy, and /readyz says we're fine",
    "exercise_type": ExerciseType.ML_DEPLOY,
    "base_app": BaseApp.PREDICTSVC,
    "difficulty": Difficulty.ADVANCED,
    "defect_class": "train_serve_skew_unversioned_spec",
    "time_limit_minutes": 45,
    "expected_time_minutes": 28,
    "databases": [],
    "needs_docker": True,
    "tags": ["fastapi", "ml", "train-serve-skew", "artifacts", "model-eval", "f1"],
    "brief_md": """\
## INC-4417 — churn risk is scoring the wrong accounts

**Severity:** SEV-2
**Reported by:** Customer Success, via #churn-risk

Tuesday's deploy shipped `churn_risk:3.0.1` — the same model version that was running
before it. Since then the daily churn-risk list has been full of accounts that CS say
are obviously healthy, while two accounts that did churn last week were never flagged.

`main` has been red since that deploy. Nobody has had time to look.

### Reproducing it

```bash
docker compose up -d --wait
make test          # red
make eval          # F1 well under the 0.80 gate CI enforces
```

### What we know

- **The service reports itself healthy.** `GET /readyz` returns `200 ready` with the
  model and spec versions it loaded. That is part of the problem, not a reassurance.
- **No code shipped in that deploy.** The diff was artifacts and a version bump that
  turned out to be a no-op.
- **The model is the one we intended to serve.** `churn_risk:3.0.1`, trained
  2025-10-02 on 48,213 rows. Retraining is not available to you — this repository
  serves models, it does not train them, and `artifacts/model_v3.json` is off limits.
- The evaluation set in `data/eval_labeled.csv` has not changed and is still 17%
  positive, which is why `make eval` leads with F1 rather than accuracy.

### Watch out for

Two independent signals are failing: the hand-computed scorer tests, and the F1 gate.
**They are not guaranteed to have the same cause.** Getting one of them green tells you
nothing about the other, and this service has more than one way to be wrong while still
looking confident. Finish by running the whole thing, not the test you started from.

CS wants to know whether last week's churn-risk list can be trusted and whether the
scores already written to the warehouse need rescoring. Answer that in `NOTES.md` — it
is read as part of your evaluation.
""",
    "definition_of_done": [
        "R1: tests/test_scorer_and_features.py::test_numeric_features_are_scaled_by_the_spec passes",
        "R2: tests/test_scorer_and_features.py::test_linear_predictor_matches_hand_computation passes",
        "R3: python eval/run_eval.py reports F1 at or above the 0.80 gate",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md says whether last week's scores can be trusted and whether the "
        "warehouse needs rescoring, not just what line changed",
    ],
    "focus_paths": [
        "artifacts/feature_spec.json",
        "svc/features/pipeline.py",
        "svc/model/registry.py",
    ],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_scorer_and_features.py::test_numeric_features_are_scaled_by_the_spec"
            ),
            "weight": 3,
            "required": True,
            "description": "Numeric features are scaled as the shipped model expects",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_scorer_and_features.py::test_linear_predictor_matches_hand_computation"
            ),
            "weight": 3,
            "required": True,
            "description": "The hand-computed score of -4.0 is reproduced",
        },
        {
            "id": "R3",
            "kind": CheckKind.METRIC,
            "target": "python eval/run_eval.py --json",
            "expect": {"metric": "f1", "op": ">=", "threshold": 0.80},
            "weight": 4,
            "required": True,
            "description": (
                "F1 on the held-out set clears the gate CI enforces. The heaviest check: "
                "it is the only one that sees the second skewed feature"
            ),
        },
        {
            "id": "R4",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R5",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "The CI pipeline passes, artifact compatibility step included",
        },
        {
            "id": "R6",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, the CI script, the model and the spec archive are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.GREP_PRESENT,
            "target": "archive",
            "paths": ["svc/**/*.py"],
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "The serving path now knows the archive exists -- i.e. they closed the "
                "detection gap rather than only restoring the values"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Identified that assert_compatible compares names only, so no "
                "value-level spec edit can ever be caught by it, and said what would"
            ),
        },
    ],
    "baseline": baseline("ex-009-churn-scores-skewed-after-deploy"),
    "context_excerpts": [
        SKEW_EXCERPT,
        {
            "path": "svc/model/registry.py",
            "line_range": "118-152",
            "why": (
                "assert_compatible as it already exists. A fix that adds a value-level "
                "check belongs here, next to the two name-level ones; judging whether "
                "the candidate's guard fits requires seeing them."
            ),
        },
        {
            "path": "artifacts/archive/README.md",
            "line_range": "1-24",
            "why": (
                "The archive is the authoritative record of what each spec version "
                "meant, and it already documents that nothing verifies against it. A "
                "strong answer uses it as evidence; a weak one never opens it."
            ),
        },
    ],
    "hints": [
        "Reproduce both failures separately before changing anything: `make test-fast`, "
        "then `make eval`. Note which layer each failure sits in -- one is arithmetic "
        "in the scorer, the other is a metric over 400 rows.",
        "The failing scorer tests hand-compute their expected numbers, and the "
        "arithmetic is written out in the docstring. Compare each term against what the "
        "feature spec on disk actually declares for that feature.",
        "`artifacts/archive/` keeps the spec for every version ever deployed, and "
        "`artifacts/model_v3.json` names the one this model was trained against. Diff "
        "the active spec against that archived copy -- and read the whole diff, not the "
        "first hunk of it.",
    ],
    "grading_notes": """\
**Root cause.** `artifacts/feature_spec.json` still declares `"version": "2.1"`, but two
of its scales are the pre-2.1 values: `monthly_spend` is `100.0` where 2.1 uses `1000.0`,
and `support_tickets` is `1.0` where 2.1 uses `10.0`. A deploy shipped a partially
rolled-back artifact. Because the version string was untouched, `assert_compatible`'s
version check passes; because no feature was added or removed, its name check passes too.
`/readyz` therefore reports `ready` while every prediction is computed from a feature
contract the model was never trained on.

**The expected fix** restores both scales to the 2.1 values, recoverable from
`artifacts/archive/feature_spec-2.1.json`, which is byte-identical to a correct active
spec. Only two lines change.

**The discriminator, and it is measured.** The two skews are invisible to different
detectors, which is the whole point of the exercise:

- Fixing **only `monthly_spend`** makes all four hand-computed tests pass and leaves F1
  at **0.556** (precision 0.400, recall 0.912) with two tests still red. The suite
  looking *nearly* green here is what tempts people to stop.
- Fixing **only `support_tickets`** restores F1 to **0.880597** — exactly the pristine
  value, because the `monthly_spend` skew flips **zero** of the 400 eval labels — while
  four scorer tests stay red. Someone who chases the metric alone declares victory with
  a quarter of the suite failing.
- Both fixed: 71 passed, F1 0.880597.

So the grade turns on whether they ran *everything* at the end. A submission that fixed
one scale has not half-solved this; it has produced a service that is confidently wrong
in one of two directions.

**What separates a strong answer.** The brief asks whether the warehouse needs rescoring.
The honest answer is yes for everything scored since the deploy, and the candidate can
bound it: `monthly_spend` alone changed no labels on the held-out set, so the damage is
attributable almost entirely to `support_tickets` — accounts with support history were
pushed to high risk (precision collapsed to 0.400, so roughly 60% of flagged accounts
were false positives). Reasoning of that shape, rather than "restored two scales", is
what distinguishes an A.

**On the stretch.** `assert_compatible` compares names only and structurally cannot catch
a value-level edit. Any guard that closes this is worth credit: a checksum of the spec
recorded in the model artifact, or verification of the active spec against
`artifacts/archive/feature_spec-<version>.json` at load time. S1 greps for the archive
being referenced from `svc/`, which is a weak proxy -- lean on S2 and the writeup for
whether they actually understood the gap. Do not require it; the required fix is the
values.

**Common wrong turns.**

- *Fixed the loud one and stopped.* Most likely failure mode. Correctness caps at the
  failing required checks; this is not a symptom patch, it is an incomplete one, so do
  not also set `symptom_patch_suspected`.
- *Moved `clip_max` instead of `scale`* to drag F1 back up. Clipping bounds are part of
  the same contract and the archived 2.1 spec shows they were not what changed. Treat as
  a symptom patch: cap correctness around 70 and set `symptom_patch_suspected`.
- *Edited an archived spec* so it agrees with the broken active one. That is destroying
  the evidence, and `artifacts/archive/**` is protected, so the tampering gate fires.
  Hard F.
- *Bumped the active spec's `version`* to something new so `assert_compatible` raises and
  `/readyz` goes 503. Good instinct and worth saying so in feedback — failing loudly
  beats serving skew — but it stops the bleeding without fixing the values, so the
  required checks still fail.
- *Lowered the F1 threshold* in `ci/run_ci.sh` or the suite. Both protected. Hard F.
- *Tried to retrain or hand-adjust coefficients.* `artifacts/model_v3.json` is protected
  and the brief says retraining is unavailable; attempting it suggests they read the
  symptom as "the model is bad" rather than "the model is being fed the wrong features".

**On documentation.** A `NOTES.md` that names both skewed features, explains why the
registry's guard stayed quiet, and answers the rescoring question is a strong writeup. One
that describes the two-line edit without mentioning that the guard could not have caught
it has missed the part of this incident worth learning.
""",
}


# ---------------------------------------------------------------------------
# ex-010 -- fix a severe latency issue
# ---------------------------------------------------------------------------

EX010 = {
    "slug": "ex-010-predict-latency-cache-never-hits",
    "exercise_number": 10,
    "title": "/predict got 25x slower and the box is pinned on disk I/O",
    "exercise_type": ExerciseType.LATENCY,
    "base_app": BaseApp.PREDICTSVC,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "cache_key_mismatch_reloads_per_request",
    "time_limit_minutes": 35,
    "expected_time_minutes": 22,
    "databases": [],
    "needs_docker": True,
    "tags": ["fastapi", "ml", "latency", "caching", "artifacts", "profiling"],
    "brief_md": """\
## INC-4502 — scoring latency is through the roof

**Severity:** SEV-2
**Reported by:** Platform, via #predictsvc-alerts

p99 on `POST /predict` went from under a millisecond to tens of milliseconds after last
week's release, and the hosts are now spending most of their time in the kernel rather
than in Python. The nightly batch job that scores the full book used to finish in
seconds and now takes most of an hour.

**The predictions themselves are correct.** `make eval` still reports the F1 we expect,
so this is not the model — it is how much work the service does to produce each answer.

### Reproducing it

```bash
docker compose up -d --wait
make test
make bench
```

`make bench` is the instrument to trust here. It reports **operation counts** next to
the wall clock, and the counts are the number that matters: wall clock on a laptop under
Docker swings by a factor of several depending on what else is running, while the amount
of work per request does not.

### What we know

- Last week's release added the ability to roll out a new model **without restarting
  every worker** — previously a model swap meant a full redeploy. That was a real
  operational problem and somebody fixed it.
- Nothing about the model, the feature spec or the evaluation set changed.
- `make test` is red, and the test that fails says what it measured.

### Watch out for

Whatever you do, the hot-reload behaviour the release was shipped for is on the table:
it was added for a reason, and you may keep it or remove it. What you must not do is
leave it in place and non-functional, or delete it without saying why. That decision —
and the reasoning behind it — is part of what is being assessed, so put it in
`NOTES.md`.

Also: make sure your fix is actually a fix and not a faster way of being wrong. A cache
that serves a stale model is worse than a slow one that serves the right one.
""",
    "definition_of_done": [
        "R1: tests/test_scorer_and_features.py::test_the_artifacts_are_read_from_disk_once_per_process passes",
        "R2: python bench/bench_predict.py reports at most 2 artifact loads for 200 requests",
        "R3: the whole suite is green, with no test skipped, deleted or weakened",
        "R4: python eval/run_eval.py still clears the 0.80 F1 gate — the fix must not change what is predicted",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md states whether the hot-reload behaviour survives your fix, and why",
    ],
    "focus_paths": ["svc/model/registry.py", "svc/routers/predict.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_scorer_and_features.py::"
                "test_the_artifacts_are_read_from_disk_once_per_process"
            ),
            "weight": 3,
            "required": True,
            "description": "The artifacts are read from disk once, not once per request",
        },
        {
            "id": "R2",
            "kind": CheckKind.BENCHMARK,
            "target": "python bench/bench_predict.py --json",
            "expect": {"metric": "artifact_loads", "op": "<=", "threshold": 2},
            "weight": 4,
            "required": True,
            "description": (
                "200 scored requests cost at most 2 artifact loads. Measured 1 on the "
                "reference fix and 200 pre-fix, so the margin is two orders of magnitude"
            ),
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R4",
            "kind": CheckKind.METRIC,
            "target": "python eval/run_eval.py --json",
            "expect": {"metric": "f1", "op": ">=", "threshold": 0.80},
            "weight": 3,
            "required": True,
            "description": (
                "Predictions are unchanged. Guards the cheap wrong answer: caching so "
                "aggressively that a stale or mismatched artifact gets served"
            ),
        },
        {
            "id": "R5",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "The CI pipeline passes",
        },
        {
            "id": "R6",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, the CI script, the model and the spec archive are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Took an explicit position on whether hot reload should survive, rather "
                "than silently deleting a feature or silently keeping a broken one"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Noticed that even a correctly-keyed mtime cache stats both artifacts on "
                "every single request, and said what that costs"
            ),
        },
    ],
    "baseline": baseline("ex-010-predict-latency-cache-never-hits"),
    "context_excerpts": [
        {
            "path": "bench/bench_predict.py",
            "line_range": "60-95",
            "why": (
                "Shows what the benchmark actually counts -- calls to load_model, i.e. "
                "real disk reads rather than calls to the cached accessor. Needed to "
                "judge whether a candidate read their own measurement correctly."
            ),
        },
        {
            "path": "ARCHITECTURE.md",
            "line_range": "1-21",
            "why": (
                "The layering: routers hold no business logic and the scorer is a dot "
                "product. It places the cache in the registry, which is where a fix "
                "belongs -- not in the router and not in the pipeline."
            ),
        },
    ],
    "hints": [
        "`make bench` prints artifact loads per 200 requests and tells you what the "
        "number should be. Run it before you read any code, and believe the count rather "
        "than the wall clock.",
        "The cache added last week is not missing -- look at it closely. Follow one "
        "request through it and ask what value it looks the entry up by, and what value "
        "it stored the entry under.",
        "`_CACHE.get(stamp)` reads by modification-time stamp; the write a few lines "
        "below is `_CACHE[loaded.identifier]`, keyed by the model's name and version. "
        "The two keys are never equal, so the lookup can never hit.",
    ],
    "grading_notes": """\
**Root cause.** `svc/model/registry.py::get_loaded_model` looks the cache up by
`_artifact_stamp()` — the artifacts' modification times — but stores the loaded result
under `loaded.identifier`, the model's `name:version`. The two keys are never equal, so
every call misses, and every miss re-reads both JSON artifacts and re-runs
`assert_compatible`. The cache is present, plausible, and entirely dead.

**Measured.** 200 requests cost **200** artifact loads pre-fix and **1** after, with wall
clock going 196 µs/request → 7 µs/request in the container. F1 is **0.880597 in both
states**: nothing about the answers changes, which is why only the benchmark and the one
caching test notice. A candidate who leans on the eval metrics here learns nothing.

**Two fixes are equally correct**, and which one they chose matters less than whether
they chose deliberately:

1. **Keep hot reload, fix the key** — write under `stamp` instead of `identifier`. Keeps
   the operational capability the release existed to deliver. Costs two `stat()` calls
   per request forever, which is roughly a thousand times cheaper than a reload but is
   not free, and a strong answer says so (that is S2).
2. **Drop hot reload, restore `@lru_cache(maxsize=1)`** — what `reference.patch` does.
   Simpler and strictly fastest, but it silently withdraws a feature somebody shipped on
   purpose; acceptable only if they say they are doing it and why. Rolling a model out
   then becomes a redeploy again, which is a real cost to name.

Treat either as full marks on correctness. Mark *engineering* down when the choice was
clearly not noticed — a diff that deletes the reload machinery with no mention of it in
`NOTES.md` is indistinguishable from not having read it.

**Common wrong turns.**

- *Caching the `LoadedModel` in the router* (a module-level global in
  `svc/routers/predict.py`). Works, and the checks pass, but it puts state in the layer
  `ARCHITECTURE.md` says holds no business logic, and leaves the dead cache in the
  registry for the next person. Correctness full, engineering around 60.
- *Caching by `identifier` on both sides.* Now the lookup hits — but the key is derived
  from the artifact that was last loaded, so a swapped model is never picked up and the
  hot-reload feature is broken in a subtler way than before. Passes every objective
  check. If `NOTES.md` claims hot reload still works, that is a confidently wrong claim:
  cap correctness around 75 and set `symptom_patch_suspected`.
- *Widening the benchmark threshold* or editing the failing test. Both protected. Hard F.
- *Reaching for threads, locks or an LRU library.* One process, one model, read-only
  after load. Over-engineering; mark engineering down and say why.
- *Chasing the wall clock.* `us_per_request` moves with laptop load, so someone tuning
  against it will conclude noise is signal. The count is the measurement; the brief says
  so and the benchmark prints the expected value next to the actual one.

**On documentation.** The brief asks a direct question — does hot reload survive? A
`NOTES.md` that answers it, names the operational consequence of the answer, and reports
the before/after counts rather than a vague "it's faster now" is an A-grade writeup. One
that says "re-added the cache" has done the work and failed to show any of the judgment
the work required.
""",
}


# ---------------------------------------------------------------------------
# ex-011 -- fix a broken CI/CD pipeline
# ---------------------------------------------------------------------------

#: ex-011 repairs ``ci/run_ci.sh``, so that file cannot be protected here the way it is
#: everywhere else. The workflow takes its place as the immovable reference: it is the
#: half that is still correct, so the drift has exactly one right direction to be closed
#: in, and "edit the workflow down to match the script" stops being available.
CI_EXERCISE_PROTECTED = [
    "tests/**",
    "pytest.ini",
    "artifacts/**",
    ".github/workflows/ci.yml",
]

#: Proves the property the exercise is actually about: not "does CI pass" but "can CI
#: fail". Copies the repo to a scratch directory, plants a failing test, and requires
#: ``ci/run_ci.sh`` to exit non-zero. Run against a copy so the candidate's workspace is
#: never touched. Measured: exits 1 on the fixed script, 0 on the mutated one.
CI_CAN_FAIL_PROBE = (
    'd=$(mktemp -d); cp -r . "$d"; cd "$d"; '
    r"printf 'def test_ci_gate_probe():\n    assert False\n' > tests/test_zz_ci_gate_probe.py; "
    "bash ci/run_ci.sh >/dev/null 2>&1 && exit 1 || exit 0"
)

EX011 = {
    "slug": "ex-011-ci-green-while-the-model-regressed",
    "exercise_number": 11,
    "title": "CI has been green for three weeks and we shipped a model that scores 0.42",
    "exercise_type": ExerciseType.CICD_PIPELINE,
    "base_app": BaseApp.PREDICTSVC,
    "difficulty": Difficulty.BEGINNER,
    "defect_class": "ci_script_cannot_fail",
    "time_limit_minutes": 25,
    "expected_time_minutes": 15,
    "databases": [],
    "needs_docker": True,
    "tags": ["ci", "bash", "github-actions", "quality-gates", "ml-eval"],
    "brief_md": """\
## INC-4610 — the pipeline passed something it should have blocked

**Severity:** SEV-3 (no customer impact yet — we caught it in review)
**Reported by:** Aoife, via #predictsvc

A candidate model with an F1 of **0.42** was merged last Thursday. It should have been
impossible: CI enforces `F1 >= 0.80` and the pipeline reported a green tick. It was
reverted before it reached anyone, and the question now is why nothing stopped it.

Since then we noticed CI has reported green on *every* run for about three weeks.

### Reproducing it

```bash
docker compose up -d --wait
make test          # green -- the application code is fine
make ci            # read this output carefully, all of it
```

**`make test` passing is not the thing to check here.** The test suite is healthy. What
is broken is the pipeline that is supposed to stop bad work from merging.

To see it for yourself, make something genuinely fail and watch what the pipeline says:

```bash
d=$(mktemp -d); cp -r . "$d"; cd "$d"
printf 'def test_deliberately_broken():\n    assert False\n' > tests/test_scratch.py
bash ci/run_ci.sh; echo "exit code: $?"
```

### What we know

- `.github/workflows/ci.yml` is what GitHub runs; `ci/run_ci.sh` is its executable
  mirror and is what runs locally **and in grading**. The header of each says that
  changing one means changing the other.
- Nobody has touched the application code, the model or the evaluation set.
- The workflow is believed to be correct. The local script has been edited a few times
  over the last month to make it quicker to run.

### Watch out for

Getting `bash ci/run_ci.sh` to exit 0 is not the goal — **it already does.** That is the
whole problem. The goal is a pipeline that exits non-zero when something is wrong, and
you should not trust it until you have watched it fail on purpose.

Write down in `NOTES.md` why three weeks of green ticks told us nothing, and what you
would do so these two files cannot drift apart again.
""",
    "definition_of_done": [
        "R1: bash ci/run_ci.sh exits 0 on the unmodified repository",
        "R2: bash ci/run_ci.sh exits non-zero when a test in the suite fails",
        "R3: ci/run_ci.sh enforces the F1 gate the workflow enforces",
        "R4: the whole suite is still green, with no test skipped, deleted or weakened",
        "llm: NOTES.md explains why a green tick meant nothing, and how to stop the "
        "script and the workflow drifting again",
    ],
    "focus_paths": ["ci/run_ci.sh", ".github/workflows/ci.yml"],
    "protected_paths": [*CI_EXERCISE_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": (
                "The pipeline runs clean on good code. Already true pre-fix -- it is "
                "here so a fix cannot be 'make it fail always'"
            ),
        },
        {
            "id": "R2",
            "kind": CheckKind.CMD,
            "target": CI_CAN_FAIL_PROBE,
            "expect": {"exit_code": 0},
            "weight": 5,
            "required": True,
            "description": (
                "The decisive check: with a failing test planted in a scratch copy, "
                "ci/run_ci.sh must exit non-zero. Pre-fix it exits 0"
            ),
        },
        {
            "id": "R3",
            "kind": CheckKind.GREP_PRESENT,
            "target": r"--assert-f1",
            "paths": ["ci/run_ci.sh"],
            "weight": 3,
            "required": True,
            "description": "The F1 gate the model regression walked through is enforced again",
        },
        {
            "id": "R4",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 2,
            "required": True,
            "description": "The suite is still green; it was never the problem",
        },
        {
            "id": "R5",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*CI_EXERCISE_PROTECTED],
            "weight": 0,
            "required": True,
            "description": (
                "Tests, artifacts and the workflow are untouched. The workflow is the "
                "reference the script has to be brought back to"
            ),
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Proposed or implemented something structural that stops the script and "
                "the workflow drifting apart again, rather than only re-syncing them"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Said plainly that a passing test suite was never evidence the pipeline "
                "worked, and that the two were never connected"
            ),
        },
    ],
    "baseline": baseline("ex-011-ci-green-while-the-model-regressed"),
    "context_excerpts": [
        {
            "path": ".github/workflows/ci.yml",
            "line_range": "1-36",
            "why": (
                "The correct half of the mirror, and therefore the answer key for the "
                "drift. Needed to judge whether the candidate restored the steps the "
                "workflow runs or invented their own."
            ),
        },
        {
            "path": "README.md",
            "line_range": "71-76",
            "why": (
                "States that the workflow and ci/run_ci.sh are mirrors and that changing "
                "one means changing the other -- the rule that was broken."
            ),
        },
    ],
    "hints": [
        "`make ci` already prints something that is not right, before it claims success. "
        "Read every line of its output rather than only the last one.",
        "Compare `ci/run_ci.sh` against `.github/workflows/ci.yml` step by step. The "
        "workflow is the one believed to be correct, and there is more than one "
        "difference.",
        "Look at the very top of the script, at the `set` line, and read `help set` on "
        "what `-e` does. Without it every command's failure is discarded and the script "
        "runs to its final `echo` regardless.",
    ],
    "grading_notes": """\
**Root cause.** Three edits to `ci/run_ci.sh`, all drift away from
`.github/workflows/ci.yml`, which is unchanged and correct:

1. `set -euo pipefail` became `set -uo pipefail`. **This is the one that matters.**
   Without `-e` a failing step does not abort the script, so it always reaches its final
   `echo "CI passed."` and exits 0. The pipeline is structurally incapable of failing.
2. `python eval/run_eval.py --assert-f1 0.80` became `python eval/run_eval.py --json >
   /dev/null`. The F1 gate is not enforced locally at all, which is the specific hole the
   0.42 model walked through.
3. `python bench/bench_predict.py --json` became `--jsonl`, an unrecognised argparse
   flag. This one is *visible*: `make ci` prints `error: unrecognized arguments: --jsonl`
   and then says `CI passed.` on the next line.

**The expected fix** restores all three, i.e. brings the script back into step with the
workflow. Two lines and one character.

**Measured.** Mutated: `bash ci/run_ci.sh` exits 0, and still exits 0 with a deliberately
failing test planted in the suite. Fixed: exits 0 clean, exits 1 with the same planted
test. The suite is **72 passed in both states** — the application code is untouched, and
a candidate who spends their time looking for a code bug has misread the brief.

**What separates a strong answer.** Fault 3 is loud and fault 2 is findable by diffing
the two files. Fault 1 is the one with the lesson in it, and the thing to look for is
whether they understood the *order* of consequence: without `-e`, faults 2 and 3 could
never have been caught by CI either, and neither could any future one. A writeup that
lists three unrelated edits has fixed the script; one that explains that the first edit
made the other two undetectable has understood the incident.

The other thing worth real credit is whether they verified by watching it fail. The brief
hands them the command. A `NOTES.md` that reports the exit code before and after is doing
the one thing that would have caught this three weeks ago.

**Common wrong turns.**

- *Fixed only the `--jsonl` typo* because it was the visible error, leaving a pipeline
  that still cannot fail. R2 and R3 catch it. This is the most likely failure mode and it
  is the whole point of the exercise, so grade it honestly: the required checks fail.
- *Added `|| exit 1` after each step* instead of restoring `set -e`. Works, and R2 passes.
  It is more verbose and easier to forget on the next step added, so mark engineering down
  modestly and say why — but this is a legitimate fix, not a symptom patch.
- *Edited `.github/workflows/ci.yml` down to match the broken script.* Protected, so the
  tampering gate fires. Worth noting in feedback that this is the direction of drift
  closure that makes an incident permanent.
- *Deleted the eval or benchmark step* to get a clean run. R3 catches the eval case
  directly; a deleted benchmark step passes the checks but is a silent reduction in
  coverage — if `NOTES.md` does not mention it, treat as a symptom patch and set
  `symptom_patch_suspected`.
- *Changed `--assert-f1 0.80` to a lower bar* so it cannot fail. R3 only greps for the
  flag, so read the value: anything below 0.80 contradicts the workflow and is the same
  defect in a new costume.

**On the stretch.** The structural answer is that two files which must agree should not
both be hand-maintained: generate one from the other, have the workflow call
`ci/run_ci.sh` directly as its single step, or add a check that diffs the step lists.
Having the workflow just run the script is the cleanest and is worth full stretch credit.
Proposing it in `NOTES.md` counts; implementing it is not required at this time limit.
""",
}


# ---------------------------------------------------------------------------
# ex-012 -- fix an evaluation framework
# ---------------------------------------------------------------------------

EX012 = {
    "slug": "ex-012-eval-framework-flatters-the-model",
    "exercise_number": 12,
    "title": "Offline F1 says 0.89, the churn list says otherwise",
    "exercise_type": ExerciseType.EVAL_FRAMEWORK,
    "base_app": BaseApp.PREDICTSVC,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "metric_formula_errors_masked_by_degenerate_fixtures",
    "time_limit_minutes": 30,
    "expected_time_minutes": 18,
    "databases": [],
    "needs_docker": True,
    "tags": ["ml", "model-eval", "f1", "precision-recall", "metrics", "test-design"],
    "brief_md": """\
## INC-4703 — we do not trust the evaluation numbers any more

**Severity:** SEV-3
**Reported by:** Data Science, via #churn-risk

Two things that should not both be true:

- `make eval` reports **precision 0.8939 and recall 0.8939** — identical to four decimal
  places, run after run.
- Customer Success, working the churn list by hand, reckons we are missing roughly one
  churner in eight. That is not what a recall of 0.89 looks like.

Nobody has been able to reproduce a problem in the *model*. The suspicion has moved to
the thing measuring it.

### Reproducing it

```bash
docker compose up -d --wait
make test
make eval
```

### What we know

- The model, the feature spec and the evaluation set are all unchanged and are **not**
  what you are looking for. `artifacts/` is off limits.
- The confusion matrix itself — 59 true positives, 7 false positives, 325 true
  negatives, 9 false negatives — has been checked by hand against the labelled set and
  is right. Whatever is wrong happens *after* the counting.
- CI enforces `F1 >= 0.80` and has been passing throughout.

### Watch out for

The reported F1 went **up**, not down. A gate that only ever asks "is this number big
enough" cannot catch a measurement error that inflates the number, and this one has been
passing the whole time — so do not treat the green F1 gate as evidence of anything.

When you are done, `NOTES.md` should answer the uncomfortable question: the test suite
has covered these metrics since the project started, and every one of those tests passed
with this bug in place. Why?
""",
    "definition_of_done": [
        "R1: tests/test_api_and_eval.py::test_f1_is_the_harmonic_mean_not_the_average passes",
        "R2: tests/test_api_and_eval.py::test_precision_and_recall_are_not_interchangeable passes",
        "R3: tests/test_api_and_eval.py::"
        "test_the_majority_baseline_holds_when_the_positive_class_is_the_majority passes",
        "R4: python eval/run_eval.py reports the model's true F1 of 0.880597",
        "R5: the whole suite is green, with no test skipped, deleted or weakened",
        "R6: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md explains why the pre-existing metric tests all passed with these "
        "bugs present",
    ],
    "focus_paths": ["eval/metrics.py", "eval/run_eval.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_api_and_eval.py::test_f1_is_the_harmonic_mean_not_the_average",
            "weight": 3,
            "required": True,
            "description": "F1 is the harmonic mean, pinned where precision and recall diverge",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_api_and_eval.py::test_precision_and_recall_are_not_interchangeable"
            ),
            "weight": 3,
            "required": True,
            "description": "Recall is computed over the actual positives, not the predicted ones",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_api_and_eval.py::"
                "test_the_majority_baseline_holds_when_the_positive_class_is_the_majority"
            ),
            "weight": 2,
            "required": True,
            "description": "The majority baseline is the larger class rate, not the negative rate",
        },
        {
            "id": "R4",
            "kind": CheckKind.METRIC,
            "target": "python eval/run_eval.py --json",
            "expect": {"metric": "f1", "op": "==", "threshold": 0.880597},
            "weight": 4,
            "required": True,
            "description": (
                "The headline figure is exactly right again. Equality, not a floor: the "
                "defect inflated F1 to 0.893939, which any >= 0.80 gate waves through"
            ),
        },
        {
            "id": "R5",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R6",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "The CI pipeline passes",
        },
        {
            "id": "R7",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, the CI script, the model and the spec archive are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Worked out *why* the old tests missed it -- the one hand-computed "
                "fixture has fp == fn, so precision equals recall in it and it cannot "
                "distinguish the formulas -- rather than only fixing the formulas"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Observed that a one-sided threshold cannot catch a metric error that "
                "raises the score, and said what would"
            ),
        },
    ],
    "baseline": baseline("ex-012-eval-framework-flatters-the-model"),
    "context_excerpts": [
        {
            "path": "eval/metrics.py",
            "line_range": "1-12",
            "why": (
                "States why F1 leads and why the majority baseline is reported next to "
                "accuracy. The reasoning a correct implementation has to match."
            ),
        },
        {
            "path": "tests/test_api_and_eval.py",
            "line_range": "167-176",
            "why": (
                "test_metrics_are_hand_computable, the pre-existing fixture. tp=3 fp=1 "
                "tn=5 fn=1 -- fp == fn, so precision == recall == 0.75 and the harmonic "
                "and arithmetic means coincide. This is the file that let all three "
                "defects through, and a strong answer identifies it by name."
            ),
        },
    ],
    "hints": [
        "Start from the symptom in the brief rather than the code: precision and recall "
        "are reported as the same number to four decimal places. For that to happen on "
        "400 rows, what would have to be true of how one of them is computed?",
        "Read the three failing tests before touching anything. Each names the property "
        "it is checking, and between them they cover three separate formulas in "
        "`eval/metrics.py`.",
        "`recall` divides by `true_positive + false_positive`, which is precision's "
        "denominator; it should be `true_positive + false_negative`. `f1` returns "
        "`(p + r) / 2` rather than `2pr / (p + r)`. `majority_baseline_accuracy` "
        "returns `1 - rate` rather than `max(rate, 1 - rate)`.",
    ],
    "grading_notes": """\
**Root cause.** Three independent formula errors in `eval/metrics.py`, all of which the
suite passed:

1. `recall` divides by `true_positive + false_positive` — precision's denominator. On the
   shipped matrix that makes recall report 0.893939, identical to precision, which is the
   symptom in the brief.
2. `f1` returns `(precision + recall) / 2`, the arithmetic mean, instead of
   `2pr / (p + r)`.
3. `majority_baseline_accuracy` returns `1 - positive_rate` instead of
   `max(rate, 1 - rate)`.

**The expected fix** is three one-line corrections. The work is not the editing.

**Measured, and this is what the exercise is for.** With all three defects present,
**72 of the 75 tests pass** — every single pre-existing metric test among them. Only the
three tests that were added for exactly these cases fail. Reported F1 goes *up*, from the
true **0.880597** to **0.893939**, so the `--assert-f1 0.80` gate in CI passed throughout.
And defect 3 is invisible on this dataset entirely: the negatives are the majority, so
`1 - rate` and `max(rate, 1 - rate)` both give 0.83.

**Why the old tests missed it, which is the real lesson.** `test_metrics_are_hand_computable`
uses tp=3 fp=1 tn=5 fn=1. Because **fp == fn**, precision and recall are both 0.75 in that
fixture — so it cannot tell them apart, cannot tell `tp/(tp+fp)` from `tp/(tp+fn)`, and
cannot tell a harmonic mean from an arithmetic one, since those coincide whenever the two
inputs are equal. The other metric tests use all-zero or all-negative matrices, where the
same collapse happens. The suite was testing that the arithmetic ran, not that it was the
right arithmetic.

A submission that fixes three lines has done the task. A submission that says *that* has
understood it, and it is the difference between a B and an A here. S1 is the check for it.

**Common wrong turns.**

- *Fixed `recall` only*, because it is the one the brief's symptom points at. F1 then
  reads 0.880793 — within 0.0002 of correct, and R4's equality check is what catches it.
  Partial credit on correctness; the required checks fail.
- *Changed the F1 gate* in `ci/run_ci.sh`, or edited the three failing tests. Both
  protected. Hard F.
- *Went after the model or the feature spec.* The brief says the confusion matrix was
  hand-checked and `artifacts/` is off limits; this is a reading failure, and worth
  saying so plainly in feedback.
- *Imported scikit-learn's `f1_score`.* It is not in `requirements.txt` and the whole
  service is deliberately dependency-free for reproducibility — `requirements.txt` says
  so in a comment. Would not install in the container. Mark engineering down and note
  that the right instinct (use a trusted implementation) ran into a stated constraint
  they should have read.
- *Added their own tests but left a formula wrong.* Good instinct, incomplete job. Credit
  it in engineering, but correctness follows the checks.

**On documentation.** The brief asks directly why the tests passed. An answer that names
the degenerate fixture, and ideally notes that a one-sided `>=` threshold can never catch
an error that inflates a metric, is a strong writeup. "Fixed the recall denominator, the
F1 formula and the baseline" is accurate and misses everything that made this incident
possible.
""",
}


# ---------------------------------------------------------------------------
# ex-013 -- fix a critical bug fast
# ---------------------------------------------------------------------------

EX013 = {
    "slug": "ex-013-churn-list-flags-everyone",
    "exercise_number": 13,
    "title": "SEV-1: the churn list tripled overnight and CS is calling healthy accounts",
    "exercise_type": ExerciseType.CRITICAL_BUG,
    "base_app": BaseApp.PREDICTSVC,
    "difficulty": Difficulty.BEGINNER,
    "defect_class": "clip_applied_before_scaling",
    "time_limit_minutes": 25,
    "expected_time_minutes": 15,
    "databases": [],
    "needs_docker": True,
    "tags": ["fastapi", "ml", "feature-engineering", "scaling", "clipping"],
    "brief_md": """\
## INC-4788 — we are flagging everyone

**Severity:** SEV-1
**Reported by:** Customer Success, via #churn-risk — escalated

This morning's churn-risk list has **174 accounts** on it. Yesterday's had 66. CS started
working it from the top and the first four calls were to our largest, longest-tenured
enterprise customers — none of whom are going anywhere. Two of them asked why we were
checking in.

Outbound calls on the list are paused until this is fixed.

### Reproducing it

```bash
docker compose up -d --wait
make test
make eval
```

### What we know

- **The model is innocent.** `artifacts/` is unchanged and off limits. It is
  `churn_risk:3.0.1` against feature spec 2.1, the same pair that produced yesterday's
  sensible list.
- `make eval` puts precision at **0.356** — roughly two in three flagged accounts are
  false positives — while recall has gone *up*. We are not missing churners; we are
  drowning in accounts that are fine.
- The accounts being wrongly flagged are the big ones: many seats, high spend, years of
  tenure. The accounts at the top of yesterday's list are still there.

### Watch out for

Look at what the three features that are *supposed* to protect an account — seats, spend,
tenure — are worth by the time the model sees them. The brief's symptom is a direct clue:
if a 300-seat account and a 3-seat account arrive at the scorer looking the same, the
model cannot tell them apart no matter how good it is.

The feature contract is written down in the code that defines it. Find the place that
states the rule this implementation is breaking, and quote it in `NOTES.md` when you
explain the fix.
""",
    "definition_of_done": [
        "R1: tests/test_scorer_and_features.py::test_numeric_features_are_clipped passes",
        "R2: tests/test_scorer_and_features.py::test_numeric_features_are_scaled_by_the_spec passes",
        "R3: tests/test_scorer_and_features.py::test_linear_predictor_matches_hand_computation passes",
        "R4: python eval/run_eval.py reports the model's true F1 of 0.880597",
        "R5: the whole suite is green, with no test skipped, deleted or weakened",
        "R6: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md names the documented rule the implementation was breaking",
    ],
    "focus_paths": ["svc/features/pipeline.py"],
    "protected_paths": [*ARTIFACTS_FROZEN],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_scorer_and_features.py::test_numeric_features_are_clipped",
            "weight": 3,
            "required": True,
            "description": "Clipping is applied to the scaled value, not the raw one",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_scorer_and_features.py::test_numeric_features_are_scaled_by_the_spec"
            ),
            "weight": 3,
            "required": True,
            "description": "Numeric features reach the model at their trained magnitude",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_scorer_and_features.py::test_linear_predictor_matches_hand_computation"
            ),
            "weight": 2,
            "required": True,
            "description": "The hand-computed score of -4.0 is reproduced",
        },
        {
            "id": "R4",
            "kind": CheckKind.METRIC,
            "target": "python eval/run_eval.py --json",
            "expect": {"metric": "f1", "op": "==", "threshold": 0.880597},
            "weight": 4,
            "required": True,
            "description": (
                "F1 is exactly restored. Equality rather than a floor so a fix that gets "
                "close without being right does not pass -- pre-fix it is 0.512397"
            ),
        },
        {
            "id": "R5",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R6",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "The CI pipeline passes",
        },
        {
            "id": "R7",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*ARTIFACTS_FROZEN],
            "weight": 0,
            "required": True,
            "description": (
                "Tests, the CI script and the whole of artifacts/ are untouched. Freezing "
                "the active spec here is what makes retuning clip_max tampering rather "
                "than an alternative fix"
            ),
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Made the units argument explicitly -- the spec's bounds are expressed "
                "in scaled units, so retuning them would have been the wrong repair even "
                "though it would have turned the tests green"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Explained why the error pushed predictions towards churn specifically: "
                "the three crushed features all carry negative, protective weights"
            ),
        },
    ],
    "baseline": baseline("ex-013-churn-list-flags-everyone"),
    "context_excerpts": [
        {
            "path": "svc/features/pipeline.py",
            "line_range": "26-52",
            "why": (
                "The FeatureDef docstring, which states that clip_min/clip_max are "
                "'applied after scaling'. This is the only written statement of the rule "
                "and the mutation does not touch it, so it is both the authority the fix "
                "has to satisfy and the clue that survives in the workspace."
            ),
        },
        {
            "path": "artifacts/feature_spec.json",
            "line_range": "1-40",
            "why": (
                "Shows the scales and bounds together: seats scale 100 with clip_max 10 "
                "means 'clamp at 1,000 seats', not 'clamp at 10 seats'. Needed to judge "
                "whether the candidate understood the units or just reordered lines "
                "until the tests went green."
            ),
        },
    ],
    "hints": [
        "Run `make eval` and compare precision with recall. Flagging too many accounts "
        "rather than too few tells you which direction the scores moved, and the model's "
        "coefficients tell you which features would have to change to move them that way.",
        "Print the feature vector for one large account and read the numbers: "
        "`build_features(spec, payload)` for a 300-seat, high-spend, multi-year account. "
        "Compare each value against what `artifacts/feature_spec.json` says it should be.",
        "`_apply_bounds` in `svc/features/pipeline.py` applies `clip_min`/`clip_max` "
        "before dividing by `scale`. The bounds in the spec are expressed in *scaled* "
        "units, so they have to be applied last -- which is what the `FeatureDef` "
        "docstring a few lines above says.",
    ],
    "grading_notes": """\
**Root cause.** `svc/features/pipeline.py::_apply_bounds` clips the raw value and then
divides by `scale`, instead of scaling first and clipping the result. Every numeric
feature in the spec has a `clip_max` expressed in scaled units — `seats` is scale 100 with
`clip_max` 10, meaning "clamp at 1,000 seats" — so applying the bound to the raw number
clamps at 10 *seats* and then divides by 100.

**Measured.** The vector for a 100-seat, $1,000/month, one-year account goes from
`seats 1.0, monthly_spend 1.0, tenure_days 1.0` to `0.1, 0.05, 0.0274`. All three of
those coefficients are negative (-0.8, -0.5, -1.1), so crushing them towards zero removes
the protection a large, established, high-spend account is supposed to earn. The result:
false positives go from **7 to 112**, precision from 0.894 to **0.356**, F1 from
**0.880597 to 0.512397** — while recall *rises* to 0.912. Seven tests fail, 70 pass.

That asymmetry is the diagnostic worth rewarding. The service is not randomly wrong; it is
wrong in one direction, because the features destroyed were all protective. S2 checks
whether the candidate reasoned from the symptom to the mechanism rather than just finding
a failing test.

**The expected fix** restores scale-then-clip. Six lines, or three if written as the
original was.

**Common wrong turns.**

- *Retuned `clip_max` in the spec* so the bounds work in raw units — e.g. `seats`
  `clip_max` 10 → 1000. This would make the tests and F1 come back while leaving the code
  contradicting the `FeatureDef` contract, silently redefining what archived spec 2.1
  means, and guaranteeing the next spec from the training team arrives in scaled units and
  breaks again. `artifacts/**` is protected for this exercise precisely so this is the
  tampering gate rather than a judgement call. If they argue for it in `NOTES.md` without
  doing it, that is worth discussing in feedback — it is a real misunderstanding of which
  side owns the units, not a cheap shortcut.
- *Removed clipping altogether.* Tests pass on this dataset because no eval row exceeds a
  bound after scaling. It discards the outlier protection the spec asks for, and a single
  10,000-seat account would then dominate its own prediction. Mark correctness down and
  say what it costs.
- *Edited `artifacts/model_v3.json` to compensate.* Protected. Hard F, and it is the
  wrong instinct twice over: the model is fine and retraining is not available here.
- *Fixed the order but hardcoded the scales* in the pipeline rather than reading the
  spec. Contradicts the entire design — the spec is data precisely so serving cannot
  diverge from training. Correctness full, engineering around 50.

**On documentation.** This is a one-line conceptual error with a three-line fix, so the
writeup carries more of the grade than usual. A strong `NOTES.md` cites the
`FeatureDef` contract ("applied after scaling"), states the units argument (the bounds are
in scaled units), and explains the one-directional symptom. One that says "swapped two
lines so the tests pass" has not demonstrated that they know why the original order was
wrong, and should not clear a B−.

Note for the reviewer: the mutation rewrites `_apply_bounds`'s own docstring to describe
the wrong order, so a candidate reading only that function sees a docstring that agrees
with the broken code. The surviving statement is on `FeatureDef.clip_min`. Finding it is
part of the exercise and worth noting when they do.
""",
}


# ---------------------------------------------------------------------------
# ex-014 -- implement and deploy an ML model
# ---------------------------------------------------------------------------

EX014 = {
    "slug": "ex-014-churn-list-came-back-empty",
    "exercise_number": 14,
    "title": "Nobody is at risk any more, and accuracy says 82.5%",
    "exercise_type": ExerciseType.ML_DEPLOY,
    "base_app": BaseApp.PREDICTSVC,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "weights_matched_by_position_not_name",
    "time_limit_minutes": 30,
    "expected_time_minutes": 18,
    "databases": [],
    "needs_docker": True,
    "tags": ["fastapi", "ml", "serving", "feature-alignment", "model-eval"],
    "brief_md": """\
## INC-4820 — the churn list came back empty

**Severity:** SEV-1
**Reported by:** Customer Success, via #churn-risk

This morning's churn-risk list has **nothing on it**. Not a short list — an empty one.
Two accounts that cancelled last week were never flagged.

The awkward part: the deploy that went out yesterday was reviewed and approved, and the
dashboard still shows **82.5% accuracy**, which is why nobody noticed until CS asked
where their list had gone.

### Reproducing it

```bash
docker compose up -d --wait
make test
make eval
```

### What we know

- `make eval` reports **F1 0.0, precision 0.0, recall 0.0**, with zero true positives
  against 68 actual churners. Accuracy is 0.825 — and the majority baseline printed
  right next to it is **0.83**. We are doing worse than a service that always answered
  "no".
- `artifacts/` is unchanged and off limits. The model and spec are the same pair that
  produced a sensible list the day before.
- Yesterday's deploy contained one performance change to the scoring hot path. It was
  described in review as "no behaviour change".

### Watch out for

**Accuracy is not the number to watch here, and the evaluator tells you why** — it prints
the majority-class baseline immediately beneath it. On a set that is 17% positive, a
service that predicts "no churn" for everything scores 83%. Any fix you believe in has to
move F1, not accuracy.

The predictions are not random; they are wrong in a specific, structured way. Work out
what the scorer is actually multiplying together before you change anything, and say so
in `NOTES.md`.
""",
    "definition_of_done": [
        "R1: tests/test_scorer_and_features.py::test_feature_order_does_not_affect_the_score passes",
        "R2: tests/test_scorer_and_features.py::test_linear_predictor_matches_hand_computation passes",
        "R3: python eval/run_eval.py reports the model's true F1 of 0.880597",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md explains what was being multiplied by what, and why accuracy "
        "stayed high while the service became useless",
    ],
    "focus_paths": ["svc/model/scorer.py"],
    "protected_paths": [*ARTIFACTS_FROZEN],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_scorer_and_features.py::test_feature_order_does_not_affect_the_score"
            ),
            "weight": 4,
            "required": True,
            "description": (
                "Weights are matched to features by name, so pipeline order cannot "
                "misalign them. The test ARCHITECTURE.md names as pinning this rule"
            ),
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_scorer_and_features.py::test_linear_predictor_matches_hand_computation"
            ),
            "weight": 3,
            "required": True,
            "description": "The hand-computed score of -4.0 is reproduced",
        },
        {
            "id": "R3",
            "kind": CheckKind.METRIC,
            "target": "python eval/run_eval.py --json",
            "expect": {"metric": "f1", "op": "==", "threshold": 0.880597},
            "weight": 4,
            "required": True,
            "description": (
                "F1 exactly restored from 0.0. Deliberately not an accuracy check: "
                "accuracy was 0.825 while the service caught nothing at all"
            ),
        },
        {
            "id": "R4",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R5",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "The CI pipeline passes",
        },
        {
            "id": "R6",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*ARTIFACTS_FROZEN],
            "weight": 0,
            "required": True,
            "description": "Tests, the CI script and all of artifacts/ are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.GREP_ABSENT,
            "target": r"zip\(",
            "paths": ["svc/model/scorer.py"],
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "The positional pairing is gone rather than patched -- no zip survives "
                "in the scorer, so the weights cannot drift out of step again"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Noticed that accuracy below the majority baseline is the signature of "
                "a model predicting one class for everything, and read it that way"
            ),
        },
    ],
    "baseline": baseline("ex-014-churn-list-came-back-empty"),
    "context_excerpts": [
        {
            "path": "ARCHITECTURE.md",
            "line_range": "54-62",
            "why": (
                "States the rule directly: lookup into the vector is by name, never by "
                "position, and names the test that pins it. The authority the fix has to "
                "satisfy."
            ),
        },
        {
            "path": "artifacts/model_v3.json",
            "line_range": "1-20",
            "why": (
                "The coefficient block. Its key order happens to match the spec's output "
                "order exactly, which is why only the *sorted* ordering misaligns -- "
                "needed to judge whether the candidate understood why this shipped "
                "through review looking like a no-op."
            ),
        },
    ],
    "hints": [
        "Compare F1 against accuracy in `make eval`, then look at the confusion matrix. "
        "Zero true positives and two false positives means the service is answering 'no "
        "churn' to almost everything -- so the scores must be coming out far lower than "
        "they should, for every account.",
        "Hand-compute one score. `test_linear_predictor_matches_hand_computation` spells "
        "out the arithmetic for a known account; run the same vector through "
        "`linear_predictor` and compare term by term which weight landed on which "
        "feature.",
        "`ModelArtifact.feature_names` returns `sorted(self.coefficients)`. The feature "
        "vector arrives in *spec* order. `linear_predictor` zips those two together, so "
        "`has_sso`'s weight is being applied to `seats`, and so on down the list.",
    ],
    "grading_notes": """\
**Root cause.** `svc/model/scorer.py::linear_predictor` pairs weights with values
positionally: it zips `model.feature_names` — which is `sorted(self.coefficients)` — with
`features.values()`, which arrives in **spec** order. Sorted gives
`has_sso, monthly_spend, plan__enterprise, plan__free, plan__team, seats,
support_tickets, tenure_days`; the vector is
`seats, monthly_spend, tenure_days, support_tickets, has_sso, plan__free, plan__team,
plan__enterprise`. Only `monthly_spend` lands on its own weight. Every other feature is
multiplied by someone else's coefficient.

The name-presence guard above the loop was left intact, so `MissingFeature` still fires
correctly and that test still passes. The defect is purely in the summation.

**Why it passed review.** The artifact's coefficient dict order is *identical* to the
spec's output order, so a reviewer checking "does this iterate the coefficients in the
right order" would have concluded yes. It is `sorted()` that breaks it, and `sorted()` is
the kind of thing added for determinism and stable logs. "No behaviour change" was a
reasonable thing to believe and wrong.

**Measured.** F1 goes **0.880597 → 0.0**: zero true positives against 68 churners, two
false positives, 330 true negatives. Accuracy is **0.825**, *below* the 0.83 majority
baseline, so the service is worse than a constant "no". 8 tests fail, 69 pass.

That accuracy figure is the thing to grade on. It is high enough to look fine on a
dashboard and it is the classic signature of a model that has collapsed onto one class —
which is exactly the reading `test_f1_is_zero_when_nothing_positive_is_predicted` exists
to teach. S2 checks whether the candidate recognised it rather than just chasing the
failing tests.

**The expected fix** restores lookup by name — `total += weight * features[name]` over
`model.coefficients.items()`. Any formulation that indexes the vector by name is correct;
S1 greps for a surviving `zip(` because a fix that keeps positional pairing and merely
sorts the vector to match is one spec reordering away from breaking again.

**Common wrong turns.**

- *Sorted the feature vector* so it lines up with `feature_names`. Every objective check
  passes. It is still positional pairing, it still contradicts `ARCHITECTURE.md`, and the
  next categorical category added to the spec silently misaligns everything again. S1
  catches the `zip`. Treat as a symptom patch: cap correctness around 70 and set
  `symptom_patch_suspected`.
- *Reordered the coefficients in `model_v3.json`.* Protected, so the tampering gate
  fires — and it would have "worked", which is worth pointing out in feedback: it makes
  the artifact responsible for a code bug forever.
- *Changed `feature_names` to return the unsorted keys.* Makes the tests pass because the
  dict order matches the spec order today. It breaks the property that
  `feature_names` is documented to have (sorted, for stable reporting) and it still
  leaves the scorer positional. Correctness around 60, engineering lower, and say why.
- *Chased accuracy.* Someone who tries to raise accuracy will be optimising towards the
  majority baseline and may conclude the model is fine. The brief warns about this
  explicitly; if the writeup treats 82.5% as nearly-working, that is a serious
  misunderstanding of imbalanced evaluation and should be reflected in the grade.

**On documentation.** A strong `NOTES.md` states which weight was landing on which
feature, explains that the coefficient dict order coincidentally matched the spec so only
`sorted()` exposed it, and reads the accuracy-below-baseline figure correctly. A writeup
that says "fixed feature alignment" has fixed the code and demonstrated none of the
reasoning the incident required.
""",
}


# ---------------------------------------------------------------------------
# ex-015 -- implement and deploy an ML model
# ---------------------------------------------------------------------------

EX015 = {
    "slug": "ex-015-every-pod-reported-ready",
    "exercise_number": 15,
    "title": "Half the fleet served 503s for twenty minutes and every pod said it was ready",
    "exercise_type": ExerciseType.ML_DEPLOY,
    "base_app": BaseApp.PREDICTSVC,
    "difficulty": Difficulty.BEGINNER,
    "defect_class": "readiness_probe_conflated_with_liveness",
    "time_limit_minutes": 25,
    "expected_time_minutes": 15,
    "databases": [],
    "needs_docker": True,
    "tags": ["fastapi", "ml", "deployment", "health-checks", "kubernetes", "docker"],
    "brief_md": """\
## INC-4851 — a bad rollout took traffic for twenty minutes

**Severity:** SEV-2
**Reported by:** Platform, via #predictsvc-alerts

Yesterday's rollout shipped to a batch of hosts where the artifact volume had not been
mounted. Those containers came up, failed to load the model, and **were sent traffic
anyway** — every `POST /predict` on them returned 503 for twenty minutes. The rollout
reported fully healthy throughout and nothing rolled back automatically.

The artifact mount is being fixed separately. **Your job is the part that let it reach
customers:** this service was supposed to make that rollout impossible.

### Reproducing it

```bash
docker compose up -d --wait
make test
curl -s localhost:$(grep WS_APP_PORT .env | cut -d= -f2)/readyz
```

Compare what `/readyz` tells you with what it is documented to tell you.

### What we know

- Predictions themselves are fine — `make eval` is unchanged. Nothing is wrong with the
  model, the spec or the scorer, and `artifacts/` is off limits.
- `README.md` and `ARCHITECTURE.md` both describe what `/healthz` and `/readyz` are each
  for, and why this service deliberately has two.
- Nobody can currently tell which model version a given host is serving by asking it.
- The orchestrator decides whether to route to a container using the healthcheck in
  `docker-compose.yml`. Our production manifests mirror that definition, so whatever is
  wrong there is wrong in both places.

### Watch out for

There are **two** things to put right, and only one of them is Python. A readiness probe
that reports the truth is no use if the thing consuming it is asking a different question.

In `NOTES.md`, state the operational difference between the two probes — what an
orchestrator does differently when liveness fails versus when readiness fails. That
distinction is the whole reason this incident was possible.
""",
    "definition_of_done": [
        "R1: tests/test_api_and_eval.py::test_readyz_reports_503_when_the_artifacts_cannot_load passes",
        "R2: tests/test_api_and_eval.py::test_readyz_reports_the_loaded_versions passes",
        "R3: the docker-compose healthcheck probes readiness, not liveness",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md states what an orchestrator does differently when liveness fails "
        "versus when readiness fails",
    ],
    "focus_paths": ["svc/routers/health.py", "docker-compose.yml"],
    "protected_paths": [*ARTIFACTS_FROZEN],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_api_and_eval.py::test_readyz_reports_503_when_the_artifacts_cannot_load"
            ),
            "weight": 4,
            "required": True,
            "description": (
                "Readiness fails when the artifacts cannot load. The property whose "
                "absence let the rollout take traffic"
            ),
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_api_and_eval.py::test_readyz_reports_the_loaded_versions",
            "weight": 3,
            "required": True,
            "description": (
                "A ready instance says which model and spec it loaded, so a host can be "
                "asked what it is serving"
            ),
        },
        {
            "id": "R3",
            "kind": CheckKind.GREP_PRESENT,
            "target": r"localhost:8000/readyz",
            "paths": ["docker-compose.yml"],
            "weight": 3,
            "required": True,
            "description": (
                "The healthcheck the orchestrator routes on probes readiness. Matched on "
                "the URL rather than the bare word, which also appears in prose"
            ),
        },
        {
            "id": "R4",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 2,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R5",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "The CI pipeline passes",
        },
        {
            "id": "R6",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*ARTIFACTS_FROZEN],
            "weight": 0,
            "required": True,
            "description": "Tests, the CI script and all of artifacts/ are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Explained the operational asymmetry: a failed liveness probe restarts "
                "the container, a failed readiness probe only removes it from rotation, "
                "so conflating them either hides a broken pod or restarts a healthy one"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Noticed that the production manifests mirror the compose healthcheck, "
                "and said that fixing one without the other leaves the incident live"
            ),
        },
    ],
    "baseline": baseline("ex-015-every-pod-reported-ready"),
    "context_excerpts": [
        {
            "path": "ARCHITECTURE.md",
            "line_range": "1-21",
            "why": (
                "The layering, including that routers hold no business logic. Relevant "
                "because the fix belongs in the router only as a call into the registry, "
                "not as its own artifact-loading logic."
            ),
        },
        {
            "path": "README.md",
            "line_range": "28-39",
            "why": (
                "States in prose why /healthz and /readyz are deliberately different, and "
                "names this exact failure: 'a deployment that conflates them will route "
                "traffic to a container whose model failed to load'. The authority for "
                "the fix, and what a good writeup should cite."
            ),
        },
    ],
    "hints": [
        "Ask the running service: `curl localhost:<WS_APP_PORT>/readyz`. Compare the "
        "fields that come back against what `README.md` says a ready instance reports.",
        "Read `svc/routers/health.py` top to bottom. Both handlers return a hardcoded "
        "answer; neither one consults the thing that would actually tell you whether this "
        "process can serve a prediction. `svc/model/registry.py` has the function that "
        "does, and it already raises a specific exception when it cannot.",
        "Two places. `readyz` has to load the model and return 503 with the reason when "
        "that raises `ArtifactError`; and the `healthcheck` in `docker-compose.yml` has "
        "to probe `/readyz` rather than `/healthz`, or nothing acts on the answer.",
    ],
    "grading_notes": """\
**Root cause, in two layers that are the same mistake.**

1. `svc/routers/health.py::readyz` returns `HealthResponse(status="ready")`
   unconditionally. It never calls `get_loaded_model`, so it cannot fail and cannot report
   the loaded versions — the response comes back with `model_version: null`. Its docstring
   asserts the false premise out loud: "the same answer as liveness: if the process is up,
   it can serve".
2. `docker-compose.yml`'s healthcheck probes `/healthz` instead of `/readyz`, and the
   comment explaining why it must be `/readyz` was deleted along with it. Even a correct
   probe would have been ignored.

**Measured.** Exactly 2 tests fail, 75 pass. `make eval` is **unchanged at F1 0.880597** —
every prediction this service returns is correct. That is the character of the exercise and
should shape the feedback: nothing is wrong with the model, the maths, or the data. What is
broken is the contract by which the platform decides whether to trust an instance, and no
amount of model-level testing would have caught it.

**The expected fix** restores the `try`/`except ArtifactError` in `readyz` — 503 with the
reason in `detail`, 200 with both versions otherwise — and points the compose healthcheck
back at `/readyz`. `healthz` must be left alone: liveness deliberately does not touch the
model, because a model that fails to load is not a reason to kill and restart a process
that will fail identically on the way back up.

**What distinguishes a strong answer.** The operational asymmetry, which S1 checks: a
failed **liveness** probe makes the orchestrator *restart* the container; a failed
**readiness** probe only takes it *out of rotation*. Conflating them in one direction
leaves a broken pod serving traffic (what happened here); conflating them in the other
direction gets healthy pods restarted in a loop. A candidate who fixes both lines without
being able to say that has done the task without learning the thing it exists to teach.

S2 picks up the brief's note that production manifests mirror the compose definition —
a fix that stops at the Python leaves the incident fully live, which is worth real credit
for noticing.

**Common wrong turns.**

- *Fixed only `readyz`.* The most likely outcome, since the two failing tests point
  straight at it and nothing in the test suite covers the compose file. R3 is the check
  that catches it. The probe now tells the truth and nothing asks it.
- *Fixed only the healthcheck.* Now the orchestrator asks the right endpoint and gets a
  hardcoded "ready". R1 and R2 catch it.
- *Made `healthz` load the model too*, so both probes agree. Passes every objective check
  and is wrong in the other direction: a container whose artifacts are missing now fails
  liveness and gets restarted forever instead of being quietly pulled from rotation. No
  check catches this, so look at `healthz` directly. Mark engineering down and explain the
  restart loop.
- *Returned 200 with `status: "unavailable"`* so the body reports the problem but the
  status code does not. An orchestrator routes on the status code; this is the original
  bug with better logging. Cap correctness around 60 and set `symptom_patch_suspected`.
- *Edited the two failing tests* or touched `artifacts/`. Protected. Hard F.

**On documentation.** The brief asks a direct question about probe semantics. An answer
that gets the restart-versus-derotate distinction right, cites the `README.md` line that
predicted this exact incident, and notes that the manifests need the same change is an A.
"Made readyz check the model and updated the healthcheck" is accurate, complete, and shows
none of the reasoning — a B− at best.
""",
}


# ---------------------------------------------------------------------------
# ex-016 -- implement and deploy an ML model
# ---------------------------------------------------------------------------

EX016 = {
    "slug": "ex-016-retuned-threshold-had-no-effect",
    "exercise_number": 16,
    "title": "We retuned the threshold for recall and the predictions did not move",
    "exercise_type": ExerciseType.ML_DEPLOY,
    "base_app": BaseApp.PREDICTSVC,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "threshold_hardcoded_instead_of_read_from_artifact",
    "time_limit_minutes": 30,
    "expected_time_minutes": 20,
    "databases": [],
    "needs_docker": True,
    "tags": ["fastapi", "ml", "deployment", "threshold-tuning", "precision-recall"],
    "brief_md": """\
## CHANGE-2214 — deploy blocked at the rehearsal stage

**Severity:** n/a — this is a blocked change, not an incident
**Raised by:** Data Science, via #churn-risk

Customer Success want more churners caught. Data Science' answer was to retune the
decision threshold down from 0.50 to **0.42** — same coefficients, same features, one
number in the artifact. Nothing needs retraining.

In the staging rehearsal the retuned artifact produced **identical predictions to the
current one.** Not similar: identical, every account, every run. The deploy is blocked.

### Reproducing it

```bash
docker compose up -d --wait
make test
```

To see the rehearsal result for yourself, score the evaluation set twice — once with the
artifact as shipped and once with its threshold replaced — and count how many labels
differ:

```python
from dataclasses import replace
from svc.model.registry import load_model, load_feature_spec
from svc.features.pipeline import build_features
from svc.model.scorer import predict
```

### Two things are being asked of you

**1. Make the threshold take effect.** Serving has to honour what the artifact says.

**2. Then tell us whether 0.42 should actually ship.** You now have a working threshold
and a labelled evaluation set, so this is a question you can answer with evidence rather
than an opinion. Put the numbers in `NOTES.md`.

### What we know and what is off limits

- `artifacts/` is **frozen for this change.** Data Science own the artifact; you are being
  asked what number to put in it, not to put it there. Do not edit it.
- `make eval` currently reports F1 0.880597 at the shipped threshold, and CI enforces
  `F1 >= 0.80`.
- Nothing is wrong with the model, the features, or the metrics code.

### Watch out for

"Lower the threshold to catch more churn" is a reasonable instinct and it is not
automatically right. Before you recommend it, find out what it costs on this model — and
note that the F1 gate CI enforces is itself a claim about which threshold is acceptable.
If your recommendation and that gate disagree, say so explicitly.
""",
    "definition_of_done": [
        "R1: tests/test_scorer_and_features.py::"
        "test_the_threshold_comes_from_the_artifact_not_a_constant passes",
        "R2: the whole suite is green, with no test skipped, deleted or weakened",
        "R3: python eval/run_eval.py still reports F1 0.880597 at the shipped threshold",
        "R4: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md gives a recommendation on shipping 0.42, with precision and recall "
        "figures measured from the evaluation set, not an opinion",
    ],
    "focus_paths": ["svc/model/scorer.py"],
    "protected_paths": [*ARTIFACTS_FROZEN],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_scorer_and_features.py::"
                "test_the_threshold_comes_from_the_artifact_not_a_constant"
            ),
            "weight": 4,
            "required": True,
            "description": (
                "The decision threshold is read from the artifact. The only automated "
                "detector -- every metric on the shipped artifact is identical either way"
            ),
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions against the pre-change baseline",
        },
        {
            "id": "R3",
            "kind": CheckKind.METRIC,
            "target": "python eval/run_eval.py --json",
            "expect": {"metric": "f1", "op": "==", "threshold": 0.880597},
            "weight": 3,
            "required": True,
            "description": (
                "Behaviour at the shipped threshold of 0.5 is unchanged. Guards the "
                "temptation to 'fix' this by making the service score differently"
            ),
        },
        {
            "id": "R4",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "The CI pipeline passes",
        },
        {
            "id": "R5",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*ARTIFACTS_FROZEN],
            "weight": 0,
            "required": True,
            "description": (
                "artifacts/ is frozen: the brief asks for a recommendation about the "
                "threshold, not for the candidate to ship one"
            ),
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Measured the trade-off instead of asserting it: reported what 0.42 does "
                "to precision and recall on the evaluation set, with figures"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Noticed that the F1 >= 0.80 gate and a 0.42 threshold are incompatible, "
                "and addressed the contradiction rather than ignoring it"
            ),
        },
    ],
    "baseline": baseline("ex-016-retuned-threshold-had-no-effect"),
    "context_excerpts": [
        {
            "path": "svc/model/scorer.py",
            "line_range": "22-48",
            "why": (
                "The ModelArtifact definition, whose `threshold` field is documented as "
                "'probability at or above which the prediction is the positive class'. "
                "The contract the serving path is ignoring."
            ),
        },
        {
            "path": "artifacts/model_v3.json",
            "line_range": "1-20",
            "why": (
                "Shows threshold sitting in the artifact alongside the coefficients, "
                "i.e. as something the training side owns and ships. Needed to judge "
                "whether the candidate understood why it does not belong in the code."
            ),
        },
    ],
    "hints": [
        "Start with the rehearsal rather than the code: score the evaluation set with the "
        "artifact as-is and again with `replace(model, threshold=0.42)`, and count "
        "differing labels. Zero differences tells you the threshold is not being consulted "
        "at all.",
        "Read `predict` in `svc/model/scorer.py` and ask where the number it compares "
        "against comes from. Then look at what `ModelArtifact` carries for exactly this "
        "purpose.",
        "`DECISION_THRESHOLD = 0.5` was extracted to a module constant and `predict` "
        "compares against it instead of `model.threshold`. For part two: sweep thresholds "
        "from 0.2 to 0.7 through `run_eval`-style scoring and look at what happens to "
        "false positives.",
    ],
    "grading_notes": """\
**Root cause.** `svc/model/scorer.py` defines `DECISION_THRESHOLD = 0.5` as a module
constant and `predict` compares against it rather than `model.threshold`. The shipped
artifact's threshold *is* 0.5, so every metric, every hand-computed test and the whole CI
pipeline behave identically — the defect is invisible to all of them. Retuning the artifact
changes **zero of 400 labels**, which is the rehearsal result in the brief.

It reads as a tidy-up: a magic number lifted into a named constant. That is why it shipped.

**Measured.** Exactly one test fails — `test_the_threshold_comes_from_the_artifact_not_a_constant`,
which exists for this and nothing else — and `ci/run_ci.sh` fails because the suite does.
`make eval` is unchanged at F1 0.880597 / precision 0.8939 / recall 0.8676. A candidate who
goes looking for a metric symptom will not find one.

**The fix** is one line: compare against `model.threshold`. Part one is nearly free, and the
grade should mostly ride on part two.

**Part two, which is the real exercise.** Measured on the held-out set:

| threshold | F1 | precision | recall | churners caught | false positives |
|---|---|---|---|---|---|
| 0.50 (shipped) | 0.880597 | 0.8939 | 0.8676 | 59 / 68 | **7** |
| 0.42 (proposed) | 0.713450 | 0.5922 | 0.8971 | 61 / 68 | **42** |
| 0.30 | 0.527660 | 0.3713 | 0.9118 | 62 / 68 | 105 |
| 0.01 | — | — | 0.9559 | 65 / 68 | 242 |

So 0.42 buys **two more churners for thirty-five more false alarms**, and the recall ceiling
is about 0.91 no matter how far the threshold drops — 0.50 already reaches most of it. The
defensible recommendation is **do not ship 0.42**: on this model a lower threshold does not
buy recall, it buys false positives, and catching more churn needs a better model rather
than a looser cutoff. A candidate who recommends shipping it *and* quantifies the precision
cost honestly has also done good work; what fails is an unquantified opinion in either
direction. That is S1, and it is weighted 2 because it is the substance here.

**S2** is the sharper observation: `F1 >= 0.80` in CI is only satisfiable at 0.50 on this
model — 0.45 gives 0.7625 and 0.55 gives 0.7027. The gate is not a general quality bar, it
is a de facto assertion that the threshold is 0.50. Anyone proposing to retune has to change
the gate in the same breath or watch CI block the deploy, and noticing that coupling is the
most valuable thing in this exercise.

**Common wrong turns.**

- *Fixed the line, answered part two with a sentence.* The most likely submission. The
  required checks all pass, so correctness is full and the grade turns on documentation and
  the stretch — which is the intended shape. Do not inflate it: an unevidenced "0.42 looks
  reasonable" is the thing the brief explicitly asked them not to do.
- *Edited `artifacts/model_v3.json` to 0.42.* Protected, so the tampering gate fires. Also
  wrong on its own terms: it would drop F1 to 0.713 and CI would correctly block it. Worth
  explaining in feedback rather than only penalising, because the instinct ("just ship it")
  is the thing the exercise is teaching against.
- *Kept `DECISION_THRESHOLD` as a fallback* — `model.threshold or DECISION_THRESHOLD`. A
  threshold of 0.0 is meaningful and documented ("predicts the positive class for
  everything"), and `0.0 or 0.5` evaluates to 0.5, so this silently overrides a legitimate
  value. Correctness around 75; mark it and explain the falsy-zero trap.
- *Lowered the F1 gate* in `ci/run_ci.sh` to make room for 0.42. The script is protected.
  Had it not been, this would be a defensible move *if argued* — note that in feedback.
- *Concluded the model should be retrained* without measuring anything. Right answer,
  no evidence. Credit the conclusion, not the reasoning.

**On documentation.** This brief asks a question with a right answer that requires
measurement. `NOTES.md` should contain numbers from the candidate's own sweep, a clear
recommendation, and ideally the gate observation. A writeup that fixes the line and says
"the threshold now comes from the artifact" has answered one of the two things asked and
should not clear a C+.
""",
}


#: Every authored ``predictsvc`` exercise, in catalog order. Complete at its planned 8.
EXERCISES: list[dict] = [EX009, EX010, EX011, EX012, EX013, EX014, EX015, EX016]
