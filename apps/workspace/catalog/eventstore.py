"""Exercises built on the ``eventstore`` base application.

Same ``(base_app, mutations)`` shape as the other catalog modules, and baselines are
likewise **measured** into ``baselines.json`` by the verification harness rather than
authored here.

What distinguishes this base app is that its defects are **statistical rather than
arithmetic**. A broken sum is a number somebody can check; a confidence interval that
has quietly become a point estimate, a change detector that catches spikes but not
shifts, or a baseline whose dispersion was inflated by the last incident all produce
output that looks exactly like working output. There is nothing to reconcile and nothing
goes red. That is why four of these six are the advanced tier: the symptom is an absence
-- an alarm that did not fire, an interval that never widens -- and the only way to see
it is to know what the statistic was supposed to do.

The other thing this app can demonstrate that a single-store app cannot: **two clocks**.
Events carry an event time and an ingest time, and ``ex-033`` turns on the difference.
"""

import json
from pathlib import Path
from typing import Any

from apps.workspace.enums import BaseApp, CheckKind, Database, Difficulty, ExerciseType

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
        KeyError: If no baseline has been measured, which should fail the seed command
            rather than silently ship an ungradeable exercise.
    """
    data = _BASELINES[slug]
    return {
        "failing_nodes": data["failing_nodes"],
        "passing_nodes": data["passing_nodes"],
        "metrics": data.get("metrics", {}),
    }


#: The tests are the proof, so editing them is tampering. Two additions specific to this
#: base app: ``data/**`` because the suite asserts exact totals over those committed
#: exports, and ``tools/gen_seed_data.py`` because regenerating them would change every
#: one of those constants -- making the data fit the code rather than the other way
#: round.
STANDARD_PROTECTED = [
    "tests/**",
    "pyproject.toml",
    "ci/run_ci.sh",
    "ci/smoke.sh",
    ".github/workflows/ci.yml",
    "data/**",
    "tools/gen_seed_data.py",
]

#: Shared context: why nothing under perfmodel/ is allowed to touch storage, and the
#: four estimator choices the module defends by name.
PURE_MODEL_EXCERPT = {
    "path": "ARCHITECTURE.md",
    "line_range": "87-122",
    "why": (
        "'The performance model is pure', which states the four estimator choices this "
        "service made on purpose -- nearest-rank, Wilson, median/MAD, Mann-Whitney, "
        "CUSUM-for-deploys -- and names the obvious alternative each one rejects."
    ),
}

#: Shared context: the event-time/ingest-time distinction, stated once.
TWO_CLOCKS_EXCERPT = {
    "path": "ARCHITECTURE.md",
    "line_range": "28-58",
    "why": (
        "'Two clocks'. States which clock the watermark runs on, why, and -- the part "
        "that matters when something has already gone wrong -- what the failure looks "
        "like: nothing goes red, and a number exported last week stops matching."
    ),
}


# ---------------------------------------------------------------------------
# ex-030 -- add analytics / statistical features
# ---------------------------------------------------------------------------

EX030 = {
    "slug": "ex-030-release-comparison-endpoint-is-unimplemented",
    "exercise_number": 30,
    "title": "We shipped a slow release because nothing could tell us it was slow",
    "exercise_type": ExerciseType.ANALYTICS_FEATURES,
    "base_app": BaseApp.EVENTSTORE,
    "difficulty": Difficulty.ADVANCED,
    "defect_class": "missing_nonparametric_comparison",
    "time_limit_minutes": 50,
    "expected_time_minutes": 32,
    "databases": [Database.MONGODB, Database.DUCKDB],
    "needs_docker": True,
    "tags": ["statistics", "nonparametric", "hypothesis-testing", "python", "fastapi"],
    "brief_md": """\
## PERF-241 — make `/v1/stats/compare` actually compare

**Requested by:** Platform, after the post-incident review
**Priority:** this sprint

On 1 April a checkout release went out at 12:30 and made the service slower. It was
signed off because the person signing it looked at the p95 chart, decided the two halves
"looked about the same", and had nothing else to look at. `/v1/stats/compare` exists, is
wired up end to end, and raises `NotImplementedError` the moment it is called.

`src/eventstore/perfmodel/nonparametric.py` is where the comparison belongs.
`mann_whitney_u` is stubbed; `rank_with_ties` and `_tie_correction` beside it are
implemented and are the house style to follow.

### What we need

A **Mann-Whitney U test** on the two latency samples. Not a t-test on the means — the
review specifically rejected one, and `ARCHITECTURE.md` says why.

Three things the review called out as non-negotiable:

- **Ties must be corrected for.** We record latency in whole milliseconds, so ties are
  not an edge case, they are most of the data.
- **A continuity correction**, since we are approximating a discrete statistic with a
  normal.
- **An effect size that does not grow with sample size.** At our traffic a one
  millisecond difference is "significant" by lunchtime; the number somebody acts on has
  to be a different number.

Small samples must be *flagged*, not refused: a canary with six requests in it still
wants an effect size, it just must not be allowed to quote a p-value.

### Reproducing it

```bash
docker compose up -d --wait
make test
```

`tests/test_nonparametric.py` already specifies the behaviour, with the rank sums and the
expected statistics derived in the docstrings. Read them before you start — they tell you
exactly what is required, sign conventions and edge cases included.

### Requirements

- No new dependencies. No scipy, no numpy, no statsmodels. `math.erf` is in the standard
  library and is all the normal CDF you need.
- Two identical samples must not divide by zero.
- Empty samples are an error.
""",
    "definition_of_done": [
        "R1: every test in tests/test_nonparametric.py passes, numeric expectations included",
        "R2: the release-comparison tests in tests/test_analytics.py pass",
        "R3: GET /v1/stats/compare answers, per tests/test_api.py",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md says why a rank test rather than a t-test, in terms of this data",
    ],
    "focus_paths": ["src/eventstore/perfmodel/nonparametric.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_nonparametric.py",
            "weight": 4,
            "required": True,
            "description": "Every nonparametric test passes, including the tie correction",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_analytics.py::test_a_slower_release_is_detected",
            "weight": 3,
            "required": True,
            "description": "compare_windows reports a regression on a separated sample",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_api.py::test_compare_endpoint_detects_a_slower_window",
            "weight": 2,
            "required": True,
            "description": "The endpoint answers instead of raising",
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
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, CI, the committed exports and the seed generator are untouched",
        },
        {
            "id": "R7",
            "kind": CheckKind.GREP_ABSENT,
            "target": r"^\s*(import|from)\s+(numpy|scipy|statsmodels|pandas)",
            "paths": ["src/eventstore/**/*.py"],
            "weight": 1,
            "required": True,
            "description": "No new numerical dependencies were introduced",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Explained the tie correction in terms of this data specifically -- "
                "whole-millisecond latencies make ties the common case, and omitting the "
                "correction overstates the variance and pulls every z towards zero"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Distinguished the p-value from the effect size as decision inputs: at "
                "this traffic significance is cheap and the rank-biserial correlation is "
                "the number worth acting on"
            ),
        },
    ],
    "baseline": baseline("ex-030-release-comparison-endpoint-is-unimplemented"),
    "context_excerpts": [
        PURE_MODEL_EXCERPT,
        {
            "path": "src/eventstore/perfmodel/nonparametric.py",
            "line_range": "1-22",
            "why": (
                "The module docstring, which states the rejection of the t-test and says "
                "the tie correction is not optional. The spec, written where the code is."
            ),
        },
        {
            "path": "src/eventstore/perfmodel/intervals.py",
            "line_range": "1-30",
            "why": (
                "A fully implemented sibling module in the same house style: pure "
                "functions, constants with reasons, edge cases handled explicitly."
            ),
        },
    ],
    "hints": [
        "Start with `tests/test_nonparametric.py::test_complete_separation_downwards`. "
        "Its docstring works the rank sum out in full, which fixes the sign convention "
        "before you write anything.",
        "U for the first sample is its rank sum minus `n_a*(n_a+1)/2`. The mean of U "
        "under the null is `n_a*n_b/2`, and `rank_with_ties` beside the stub already "
        "gives you the ranks.",
        "The tie-corrected variance subtracts a term built from the pooled tie group "
        "sizes; `_tie_correction` already computes the numerator of it. "
        "`test_the_tie_correction_is_applied` quotes both the corrected and the "
        "uncorrected z-score so you can tell which one you have implemented.",
    ],
    "grading_notes": """\
**This is build-shaped, not fix-shaped.** `mann_whitney_u` raises `NotImplementedError`;
the tests fully specify the behaviour with the arithmetic derived in their docstrings.
Fifteen tests fail until it is implemented — nine in `tests/test_nonparametric.py`, five
in `tests/test_analytics.py` and one in `tests/test_api.py`. That spread is expected and
is not a sign the mutation is too broad: the comparison endpoint is genuinely built on
this one function.

**The expected implementation.** Pool the samples, rank with ties averaged, take
`u_a = rank_sum_a - n_a*(n_a+1)/2`. Variance is
`(n_a*n_b/12) * ((N+1) - sum(t^3-t)/(N*(N-1)))`. Apply a continuity correction of 0.5
towards the mean, signed by which side U falls on, then a two-sided p-value from
`math.erf`. Effect size is the rank-biserial correlation `2U/(n_a*n_b) - 1`. Guard the
zero-variance case, which happens when every observation in both samples is identical.

**The three details that separate a strong answer:**

1. **The tie correction (S1).** Easy to skip, and the suite is built to catch it:
   `test_the_tie_correction_is_applied` asserts -0.556702 and also asserts the result is
   further from zero than the uncorrected -0.525108, so an implementation without it
   fails on the number *and* on the direction. A candidate who explains that whole
   millisecond latencies make ties the common case — not an edge case — has understood
   why it is in the requirements.
2. **p-value versus effect size (S2).** The brief asks for an effect size that does not
   grow with n and does not say the words "rank-biserial". Someone who implements it and
   then says in `NOTES.md` that significance is cheap at this traffic volume is
   demonstrating the judgement the feature exists to support.
3. **`approximation_valid`.** Small samples are flagged, not refused. A candidate who
   raises for `n < 8` has made a canary comparison impossible and failed
   `test_small_samples_are_flagged_rather_than_quoted`.

**Watch for:**

- **Implementing a t-test anyway**, usually `statistics.mean` plus a pooled standard
  error. It fails the U-statistic assertions immediately. The brief and
  `ARCHITECTURE.md` both reject it; if they did this they did not read either.
- **Adding scipy.** `scipy.stats.mannwhitneyu` is one line and is forbidden by the brief
  and caught by R7. Note in feedback that the ban is not arbitrary — the whole point of
  `perfmodel/` is that every number can be checked by hand.
- **Getting the sign backwards.** `effect_size > 0` must mean the *first* sample is
  slower. `test_complete_separation_upwards` catches it, and a candidate who flips the
  convention and then "fixes" `ReleaseComparison.regressed` to compensate has broken the
  rollback decision while making the tests pass. Treat that as a symptom patch.
- **Hardcoding.** Returning the literal expected values for the sample sizes in the tests
  passes a subset and fails the rest. If any survives, set the flag.
- **Computing U for the wrong sample.** `u_b = n_a*n_b - u_a`; using it gives exactly the
  wrong sign everywhere and is the single most common slip.

**On documentation.** The brief asks why a rank test rather than a t-test *in terms of
this data*. A good answer names the skew: latency is bounded below, unbounded above, and
dominated at the mean by retries and cold caches, so a release that made the median worse
and the tail slightly better would be scored an improvement. An answer that says
"non-parametric tests do not assume normality" has recited a textbook line without
connecting it to anything.
""",
}


# ---------------------------------------------------------------------------
# ex-031 -- add analytics / statistical features
# ---------------------------------------------------------------------------

EX031 = {
    "slug": "ex-031-deploy-check-stayed-quiet-through-a-regression",
    "exercise_number": 31,
    "title": "The deploy check stayed green while p95 moved and stayed moved",
    "exercise_type": ExerciseType.ANALYTICS_FEATURES,
    "base_app": BaseApp.EVENTSTORE,
    "difficulty": Difficulty.ADVANCED,
    "defect_class": "changepoint_detector_misses_sustained_shift",
    "time_limit_minutes": 50,
    "expected_time_minutes": 30,
    "databases": [Database.DUCKDB],
    "needs_docker": True,
    "tags": ["statistics", "change-detection", "cusum", "ewma", "observability"],
    "brief_md": """\
## PERF-308 — the deploy check did not catch the 1 April regression

**Severity:** SEV-3, but it is the second time
**Reported by:** SRE

`detect_sustained_regression` is what the deploy pipeline calls to decide whether a
release made things worse. On 1 April the 12:30 checkout release added roughly 90ms to
the median and the check reported no change. It also reported no change on the 3 March
release, which we later rolled back by hand.

It is not broken in the sense of throwing. It runs, it returns a result, and the result
says nothing happened.

### What we know

- **It still catches spikes.** The 18 March incident — one very bad minute — was flagged
  within a minute, which is why nobody suspected the detector.
- The thing it misses is the thing deploys actually do: a **small permanent shift**, where
  no individual minute looks unusual and the service is simply worse from then on.
- `tests/test_changepoint.py` contains a worked example of exactly this with the numbers
  derived by hand. It currently passes. Read it before you touch anything — it tells you
  what each of the two detectors in `perfmodel/changepoint.py` does to a one-sigma step,
  and the two answers are very different.
- Somebody changed this deliberately and left a note saying why. The reason they give is
  real and you should not simply discard it: the old behaviour did page twice in one week.

### Reproducing it

```bash
docker compose up -d --wait
make test
```

One test fails and it is the one that matters. Its docstring works the statistic out step
by step.

### What we need

The deploy check must detect a sustained one-sigma shift, and must still not fire on a
stable service. If your fix reintroduces the Friday-ramp false alarms, say in `NOTES.md`
what you would do about them — that is a design question and we would rather have your
answer than have you quietly pick one.

`ARCHITECTURE.md` states the rule this service is supposed to follow for which detector
goes where.
""",
    "definition_of_done": [
        "R1: tests/test_analytics.py::test_a_one_sigma_sustained_shift_is_detected passes",
        "R2: tests/test_analytics.py::test_a_stable_service_does_not_alarm still passes",
        "R3: the whole suite is green, with no test skipped, deleted or weakened",
        "R4: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md explains why the replacement detector could never have fired here",
    ],
    "focus_paths": ["src/eventstore/analytics.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_analytics.py::test_a_one_sigma_sustained_shift_is_detected",
            "weight": 5,
            "required": True,
            "description": (
                "A one-sigma step is detected at index 39 with the statistic at 5.5 -- the "
                "CUSUM arithmetic, not an approximation of it"
            ),
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_analytics.py::test_a_stable_service_does_not_alarm",
            "weight": 3,
            "required": True,
            "description": "No false alarm on sixty minutes of the same oscillation",
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
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, CI, the committed exports and the seed generator are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Showed arithmetically why the replacement could not have fired: the "
                "weighted mean converges to the new level, one sigma away, against a "
                "control band of 3*sigma*sqrt(alpha/(2-alpha)) = 1.26 sigma"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Engaged with the false-alarm problem that motivated the change rather "
                "than dismissing it -- a traffic ramp is a real drift and CUSUM will "
                "accumulate it -- and proposed something concrete"
            ),
        },
    ],
    "baseline": baseline("ex-031-deploy-check-stayed-quiet-through-a-regression"),
    "context_excerpts": [
        PURE_MODEL_EXCERPT,
        {
            "path": "src/eventstore/perfmodel/changepoint.py",
            "line_range": "1-25",
            "why": (
                "The module docstring: what each detector's memory does, and the rule of "
                "thumb that EWMA is for incidents and CUSUM for deploy verification. "
                "States the failure mode as 'detects eventually, usually after the deploy "
                "window has closed'."
            ),
        },
        {
            "path": "src/eventstore/analytics.py",
            "line_range": "352-390",
            "why": (
                "detect_sustained_regression itself. Its docstring and its body no longer "
                "agree, which is the kind of drift worth noticing on sight."
            ),
        },
    ],
    "hints": [
        "Run `make test`. One test fails; read its docstring, which derives the statistic "
        "for a one-sigma step observation by observation.",
        "`perfmodel/changepoint.py` exports two detectors and its module docstring says "
        "which job each is for. Compare that against what `detect_sustained_regression` "
        "in `analytics.py` actually calls.",
        "The question is not which function is 'better'. It is what a geometrically "
        "decaying memory does to a shift that never goes away: the weighted mean settles "
        "at the new level and the control band is wider than the shift, so the statistic "
        "never leaves the band. `tests/test_changepoint.py` has both numbers.",
    ],
    "grading_notes": """\
**Root cause.** `detect_sustained_regression` in `src/eventstore/analytics.py` calls
`ewma_detect` where it must call `cusum_detect`. The import at the top of the module was
changed to match, and a comment was left giving a real motivation: the CUSUM accumulator
climbed through a Friday traffic ramp and paged twice in one week.

**The expected fix** is to restore `cusum_detect` and the import. Two lines.

**The arithmetic, which the candidate should end up reproducing.** The test series is 30
observations exactly on target followed by 30 exactly one sigma above it.

| detector | behaviour on a +1 sigma step |
|---|---|
| CUSUM (k=0.5, h=5) | accumulates `1.0 - 0.5` per observation, crosses h at **index 39**, statistic exactly 5.5 |
| EWMA (alpha=0.3, L=3) | weighted mean converges to +1 sigma; band settles at `3*sqrt(0.3/1.7)` = **1.26 sigma**; never alarms |

So this is not "EWMA is slower". **EWMA cannot detect this shift at all, at any horizon.**
A candidate who states that, with the band arithmetic, has found the real answer (S1). A
candidate who says "EWMA is less sensitive" has found the right line for a vague reason.

**The design question is the other half of the exercise (S2).** The comment in the code is
not a lie — a traffic ramp is a genuine drift and CUSUM will accumulate it, so restoring
CUSUM does restore the false alarms. The brief asks what they would do. Good answers
include: resetting the accumulator per deploy window rather than running it continuously;
widening `h` and accepting a longer detection delay; de-seasonalising against the
hour-of-week baseline that already exists in `perfmodel/baseline.py` before running the
chart; or keeping both detectors with different destinations, which is what the
architecture document already prescribes. Any concrete, costed answer earns this. A
candidate who does not mention the false alarms at all has fixed the ticket and ignored
the reason the bug was introduced, which is how it comes back.

**Watch for:**

- **Tuning EWMA instead of replacing it** — dropping `control_l` to 2 or raising `alpha`.
  This can be made to pass R1 for this particular series while leaving the detector unable
  to see a smaller shift, and it will usually break R2. If R1 passes and R2 fails, that is
  what happened. If both somehow pass, it is a symptom patch: set the flag, because the
  candidate has tuned against the test rather than fixed the detector.
- **Calling both and alarming if either fires.** Not wrong, and it does pass. Note in
  feedback that it doubles the false-alarm rate the comment was complaining about, so it
  resolves the ticket by making the motivating problem worse.
- **Editing `perfmodel/changepoint.py`** to make `ewma_detect` behave like CUSUM. This
  breaks `tests/test_changepoint.py`, which pins both detectors, and is caught by R3. It
  is also the wrong layer: the statistics module is fine, the caller picked the wrong one.
- **Changing the test.** Protected. Hard F.

**A note on reading.** The docstring of `detect_sustained_regression` still says "CUSUM,
not EWMA" while the body calls EWMA. A candidate who spots that contradiction and says so
found the bug in the first minute, which is exactly the skill being tested — and the
remaining forty are then about *why*, which is where the marks are.
""",
}


# ---------------------------------------------------------------------------
# ex-032 -- add analytics / statistical features
# ---------------------------------------------------------------------------

EX032 = {
    "slug": "ex-032-anomaly-scan-went-blind-after-the-march-incident",
    "exercise_number": 32,
    "title": "Anomaly scores collapsed to nothing after a bad month went into the history",
    "exercise_type": ExerciseType.ANALYTICS_FEATURES,
    "base_app": BaseApp.EVENTSTORE,
    "difficulty": Difficulty.ADVANCED,
    "defect_class": "baseline_dispersion_inflated_by_its_own_history",
    "time_limit_minutes": 50,
    "expected_time_minutes": 32,
    "databases": [Database.DUCKDB],
    "needs_docker": True,
    "tags": ["statistics", "robust-estimation", "anomaly-detection", "seasonality"],
    "brief_md": """\
## OBS-512 — the anomaly scan has not flagged anything since March

**Severity:** SEV-3
**Reported by:** SRE, during the weekly review

`/v1/stats/anomalies` scores each minute against what that hour of the week normally
looks like. Since the March incident it has scored essentially nothing above threshold,
including two afternoons that were visibly bad on the chart.

The interesting part of the report: **it got worse immediately after a real incident went
into the history it fits on.** Before March it was flagging things. The worse the month
was, the quieter the detector became.

### What we know

- Nothing errors. The endpoint answers, the scores come back, they are just small.
- The scan fits a baseline from four weeks of history, bucketed by hour of week, and
  compares the window against it.
- Somebody changed how the baseline's centre and spread are estimated, for a reason they
  wrote down: the runbook's three-sigma threshold now applies directly instead of needing
  a threshold of its own. That is a real usability complaint.
- `tests/test_baseline.py` has a test that works the same history through both estimators
  and prints both answers. One of them is 1.73 and the other is 134.56. **They are
  computed from identical data.**

### Reproducing it

```bash
docker compose up -d --wait
make test
```

Three tests fail. Start with the one in `tests/test_baseline.py` whose name mentions last
week's incident — its docstring contains the whole derivation.

### What we need

An anomaly scan that still works when the history it learned from contains an incident,
because the history always contains an incident. If your fix means the runbook's threshold
no longer applies, say so in `NOTES.md` and say what the threshold should be — SRE will
have to change their runbook and would like to be told, not to find out.
""",
    "definition_of_done": [
        "R1: tests/test_baseline.py::test_a_median_and_a_mad_survive_last_weeks_incident passes",
        "R2: tests/test_baseline.py::test_fit_excludes_the_window_it_is_asked_to_exclude passes",
        "R3: tests/test_analytics.py::test_anomaly_scan_scores_every_minute_of_the_window passes",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md states what the scoring threshold should now be and why it changed",
    ],
    "focus_paths": ["src/eventstore/perfmodel/baseline.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_baseline.py::test_a_median_and_a_mad_survive_last_weeks_incident"
            ),
            "weight": 5,
            "required": True,
            "description": (
                "A 300ms observation against a contaminated history scores 134.56, not 1.73"
            ),
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_baseline.py::test_fit_excludes_the_window_it_is_asked_to_exclude",
            "weight": 2,
            "required": True,
            "description": "The fitted centre is the median of the surviving history",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_analytics.py::test_anomaly_scan_scores_every_minute_of_the_window"
            ),
            "weight": 3,
            "required": True,
            "description": "End to end through the warehouse: the bad minute scores above 10",
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
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, CI, the committed exports and the seed generator are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Named the mechanism as breakdown point: a standard deviation moves on one "
                "incident, a MAD needs half the history to be anomalous -- and drew the "
                "conclusion that the detector got quieter the worse the month was"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Answered the runbook question instead of ignoring it: a robust z is not a "
                "classical z, said what threshold to use, and flagged that SRE must be told"
            ),
        },
    ],
    "baseline": baseline("ex-032-anomaly-scan-went-blind-after-the-march-incident"),
    "context_excerpts": [
        PURE_MODEL_EXCERPT,
        {
            "path": "src/eventstore/perfmodel/baseline.py",
            "line_range": "1-25",
            "why": (
                "The module docstring, which states the centre-and-dispersion choice and "
                "the reason for it in one paragraph -- including the sentence about a "
                "dispersion inflated by last week's incident being what stops this week's "
                "from scoring."
            ),
        },
    ],
    "hints": [
        "Run `make test` and read the failing test in `tests/test_baseline.py` whose name "
        "mentions last week's incident. It computes the same history both ways and "
        "asserts both numbers.",
        "Look at `SeasonalBaseline.fit`. What it is estimating is right; the question is "
        "which estimator it uses for the centre and the spread, and what one incident in "
        "the history does to each of them.",
        "Thirty bad minutes in a 120-minute history move the mean from 100 to 150 and the "
        "standard deviation from near zero to 86.6, so a 300ms observation scores 1.73. "
        "The median and the median absolute deviation barely move, and the same "
        "observation scores 134.56.",
    ],
    "grading_notes": """\
**Root cause.** `SeasonalBaseline.fit` in `src/eventstore/perfmodel/baseline.py` was
changed to estimate each bucket's centre with `statistics.mean` and its dispersion with
`statistics.pstdev`, instead of a median and a scaled MAD. The comment left behind gives a
genuine usability reason: a classical z-score is what the SRE runbook's three-sigma
threshold is written against.

**The expected fix** restores `statistics.median` and `scaled_mad` for both the per-bucket
and the pooled estimates. `scaled_mad` is still present and still tested — only `fit`
stopped calling it.

**The measured contrast, on identical data.** History is 90 ordinary minutes around 100ms
plus the 30 minutes of a previous incident at 300ms; the observation scored is 300ms.

| estimator | centre | dispersion | z |
|---|---|---|---|
| mean / pstdev | 150.0 | 86.605427 | **1.73** |
| median / scaled MAD | 100.5 | 1.4826 | **134.56** |

**The transferable lesson, and S1.** The mechanism is the breakdown point. A standard
deviation is moved by a single incident; a MAD needs half the history to be anomalous
before it shifts at all. The consequence stated in the ticket — *the detector got quieter
the worse the month was* — follows directly, and a candidate who connects those two has
understood it rather than pattern-matched "use robust statistics".

**The runbook question is deliberately in the brief (S2).** Restoring the MAD makes the
reported z a robust z, which is not on the same scale as a classical one and does not mean
the same thing at 3. The person who made this change was solving a real problem badly. A
good answer says what SRE should use now and notes that they have to be told; a candidate
who silently restores the old behaviour has recreated the confusion that caused this.

**Watch for:**

- **Keeping mean/stdev and excluding more history**, e.g. widening the exclusion window or
  trimming outliers before fitting. Trimming is a defensible robust approach and if it
  passes R1 and R3 honestly, accept it and say so — but check it is a principled rule and
  not a filter tuned until the test went green. Exclusion alone does not fix this: the
  contaminating incident is in a *previous* week, not in the scored window, so no amount
  of excluding the window helps.
- **Fixing it in `analytics.anomaly_scan`** by rescaling the z after the fact. Gets R3
  green and leaves R1 red, because the baseline itself is still wrong. Wrong layer; the
  module that owns the estimate owns the bug.
- **Deleting the `MIN_DISPERSION` floor** while restoring the MAD. The floor exists because
  a bucket whose history is perfectly constant has a MAD of zero and would score every
  later observation as infinite. Removing it will not fail the suite today, which is worth
  mentioning as a latent regression.
- **Using `statistics.stdev` instead of `pstdev`** as a "fix". Changes the number slightly
  and nothing else; R1 still fails. If a candidate does this, they have not read what the
  test is comparing.
- **Editing the test to accept 1.73.** Protected. Hard F, and the clearest possible case of
  making the expectation fit the code.
""",
}


# ---------------------------------------------------------------------------
# ex-033 -- build or fix a data/ETL pipeline
# ---------------------------------------------------------------------------

EX033 = {
    "slug": "ex-033-buffered-gateway-events-never-reached-the-warehouse",
    "exercise_number": 33,
    "title": "Last month's numbers changed and this month's look fine",
    "exercise_type": ExerciseType.ETL_PIPELINE,
    "base_app": BaseApp.EVENTSTORE,
    "difficulty": Difficulty.ADVANCED,
    "defect_class": "rollup_watermark_uses_event_time",
    "time_limit_minutes": 50,
    "expected_time_minutes": 30,
    "databases": [Database.MONGODB, Database.DUCKDB],
    "needs_docker": True,
    "tags": ["etl", "mongodb", "duckdb", "watermark", "late-arriving-data"],
    "brief_md": """\
## DATA-640 — a report we sent in March does not reproduce

**Severity:** SEV-2
**Reported by:** the account team, via a customer

A customer asked us to re-send a March traffic summary. The numbers came back lower than
the ones we sent them the first time. Same window, same query, fewer requests.

Nothing is logged. Nothing is failing. `eventstore status` shows the rollup running and
the watermark advancing.

### What we know

- **The raw events are all in MongoDB.** Count them for the affected window and the count
  is right. The warehouse is what is short.
- The customer's gateway sits behind a flaky link. It buffers when the link drops and
  delivers a large catch-up batch afterwards — sometimes twenty-five minutes afterwards.
  That is expected behaviour and the pipeline is supposed to handle it.
- Our own committed exports under `data/` contain exactly this: a two-minute window of
  traffic that was held and delivered in one batch later. 16 events.
- Somebody changed how the rollup decides what to consume, and left a note saying why.
  Their stated motivation is reasonable; the mechanism they chose is not.

### Reproducing it

```bash
docker compose up -d --wait
make test
```

Three tests fail, all in `tests/test_rollup.py`. One of them sets the situation up
exactly: some traffic, the stream moving on, and then a late delivery for a minute that
has already been rolled up.

You can also watch it happen end to end:

```bash
make load
make rollup
make status
```

Compare `mongo_events` against `fact_requests`.

### What we need

Every event that reaches MongoDB must reach the warehouse, whenever it arrives, and must
land in the minute it **happened** in rather than the minute it showed up in.

`ARCHITECTURE.md` has a section on this exact distinction. The brief will not repeat it;
it is better stated there, and the failure mode it describes is the one in this ticket.

### Watch out for

A warehouse that is "complete through" some timestamp and a warehouse that has *consumed*
everything available are different claims. Only one of them is a safe thing to drive a
pipeline from.
""",
    "definition_of_done": [
        "R1: tests/test_rollup.py::test_a_late_arrival_is_loaded_and_corrects_its_bucket passes",
        "R2: tests/test_rollup.py::test_the_watermark_advances_to_the_latest_ingest_time passes",
        "R3: the late-arrival-in-another-minute test passes",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md says which reports are affected and whether they need reissuing",
    ],
    "focus_paths": ["src/eventstore/rollup.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_rollup.py::test_a_late_arrival_is_loaded_and_corrects_its_bucket",
            "weight": 5,
            "required": True,
            "description": (
                "A 27-minute-late event is consumed and its own minute goes from 3 to 4 "
                "requests, after the stream has already moved on"
            ),
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_rollup.py::test_the_watermark_advances_to_the_latest_ingest_time",
            "weight": 3,
            "required": True,
            "description": "The watermark is an ingest-time position",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_rollup.py::"
                "test_a_late_event_in_a_different_minute_only_touches_that_minute"
            ),
            "weight": 2,
            "required": True,
            "description": "Correcting history does not disturb the buckets either side",
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
            "description": "The CI pipeline passes, including the end-to-end smoke",
        },
        {
            "id": "R6",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, CI, the committed exports and the seed generator are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Explained why nothing ever went red -- the current window is always "
                "complete, so only a re-run of an old report reveals it -- and why that "
                "makes it worse than a crash, not better"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Did the blast-radius work: said that a backfill is needed, that "
                "`eventstore rollup --full` is safe because the sink is keyed on "
                "event_id, and which windows are affected"
            ),
        },
    ],
    "baseline": baseline("ex-033-buffered-gateway-events-never-reached-the-warehouse"),
    "context_excerpts": [
        TWO_CLOCKS_EXCERPT,
        {
            "path": "src/eventstore/rollup.py",
            "line_range": "1-24",
            "why": (
                "The module docstring, which states all three properties the job is built "
                "around -- ingest-time watermark, inclusive boundary, rebuild rather than "
                "increment -- and what each one is defending against."
            ),
        },
        {
            "path": "src/eventstore/models.py",
            "line_range": "1-30",
            "why": (
                "Where the two timestamps are defined, with the definition of each and the "
                "sentence about a buffering gateway delivering a twenty-minute-old batch."
            ),
        },
    ],
    "hints": [
        "`make load && make rollup && make status` on a clean stack, then compare "
        "`mongo_events` with `fact_requests`. The gap is the number of events the "
        "committed exports deliver late.",
        "`load_new_events` in `src/eventstore/rollup.py` selects documents using the "
        "stored position. Look at which field it filters on, then look at what the stored "
        "position is being set from at the bottom of the same function.",
        "An event that happened at 11:02 and arrived at 11:29 is behind a position that "
        "has already reached 11:12 in event time, so it is never selected again. Nothing "
        "fails, because the events that *did* arrive on time are all present.",
    ],
    "grading_notes": """\
**Root cause.** `load_new_events` in `src/eventstore/rollup.py` selects and sorts on
`occurred_at` instead of `received_at`, and the watermark it stores is the greatest
*event* time it saw rather than the greatest ingest time. A late delivery is therefore
behind the position before it ever arrives, and is never selected.

**The expected fix** restores both: the query filters and sorts on `received_at`, and the
watermark advances on `received_at`. Two places in one function.

**Why it is advanced.** The motivation left in the comment is correct — the data team
genuinely does want to know what period the warehouse is complete through — and the
mistake is conflating that *reporting* question with the *selection* mechanism. A
candidate who sees that distinction can also see that the right answer to the comment is a
separate completeness metric, not a different watermark. That observation is worth
rewarding even though it is not required.

**Measured.** On the committed exports: 1440 events in MongoDB, and the warehouse is short
by the 16 that the buffered gateway delivers at 12:07 for traffic served between 11:40 and
11:42. Three tests fail, all in `tests/test_rollup.py`.

**The thing worth noticing, and S1.** Nothing ever goes red. The current window is always
complete, because by definition the newest events are the ones that arrived most recently.
The defect is only visible by re-running an old report and getting a different answer —
which is exactly how the customer found it. A candidate who says that a silent correctness
bug in a pipeline is *worse* than a crash, because a crash gets fixed on the day, has
drawn the right conclusion.

**S2 is the incident work.** The fix stops the bleeding; it does not repair the warehouse.
`eventstore rollup --full` reloads from the beginning and is safe to run at any time
because `fact_requests` is keyed on `event_id` and loaded with `INSERT OR REPLACE`, and
because buckets are rebuilt rather than incremented. A writeup that says so, and says which
windows were under-reported, is doing the job the incident created. One that ends at "two
lines changed" has not.

**Watch for:**

- **Changing `$gte` to `$gt`.** Unrelated, and actively harmful: a whole ingest batch
  shares one `received_at`, so an exclusive boundary combined with the batch limit can cut
  a tie group in half and skip its remainder permanently. The module docstring explains
  this. If they do it, the suite may still pass; call it out as a latent bug introduced
  while fixing another.
- **Widening the window by subtracting a fixed lateness allowance** from the watermark —
  "look back an hour" — while still tracking event time. This passes the headline test if
  the allowance happens to exceed 27 minutes, and silently fails for any gateway that
  buffers longer. If R1 passes this way, treat it as a symptom patch: the allowance is a
  guess about somebody else's network.
- **Rebuilding every bucket on every run** instead of fixing the selection. Correct output,
  unbounded cost, and R5's smoke will still pass. Note it as a fix that does not scale.
- **Fixing it in `run_rollup` or `rebuild_buckets`.** The buckets are not the problem — the
  rows never arrive to be bucketed. A candidate who lands here has not followed the data
  far enough back.
- **Regenerating `data/` or editing the tests.** Both protected. Hard F.
""",
}


# ---------------------------------------------------------------------------
# ex-034 -- fix a critical bug fast
# ---------------------------------------------------------------------------

EX034 = {
    "slug": "ex-034-a-retried-batch-swallowed-nine-hundred-events",
    "exercise_number": 34,
    "title": "A gateway retry made most of a batch disappear",
    "exercise_type": ExerciseType.CRITICAL_BUG,
    "base_app": BaseApp.EVENTSTORE,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "ordered_insert_drops_the_rest_of_the_batch",
    "time_limit_minutes": 30,
    "expected_time_minutes": 18,
    "databases": [Database.MONGODB],
    "needs_docker": True,
    "tags": ["mongodb", "idempotency", "data-loss", "incident"],
    "brief_md": """\
## INC-2291 — we are losing events whenever a gateway retries

**Severity:** SEV-1, ongoing
**Reported by:** on-call

A gateway timed out mid-delivery at 02:14 and retried the batch. The retry reported
success. We have 112 of the 1000 events in that batch.

It has happened three times this week and it correlates exactly with retries. A delivery
that is not a retry is fine.

### What we know

- The ingest endpoint returns 202 with a receipt. On the retried batches the receipt says
  `"inserted": 0, "duplicates": 1` — **one** duplicate, in a batch where the first 112
  events were already present.
- Deduplication is supposed to be handled by the unique index on `event_id`, so that a
  retry is absorbed silently. That design has not changed.
- Someone touched the write path recently for an unrelated reason and said so in a
  comment.

### Reproducing it

```bash
docker compose up -d --wait
make test
```

Two tests fail, both in `tests/test_ingest.py`. The second one is the incident in
miniature: a batch of five where two are already present.

### What we need

A retried batch must insert everything that is not already there and report honestly how
many of each it did. Nothing in a delivery may be dropped because something earlier in it
was a duplicate.

This is a live incident — fix it first, then write it up. `NOTES.md` should say how many
events we have lost and how to get them back, not just what the change was.
""",
    "definition_of_done": [
        "R1: tests/test_ingest.py::test_a_partially_overlapping_batch_inserts_only_the_new_events passes",
        "R2: tests/test_ingest.py::test_a_retried_batch_is_absorbed_without_double_counting passes",
        "R3: the whole suite is green, with no test skipped, deleted or weakened",
        "R4: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md says what was lost and how to recover it",
    ],
    "focus_paths": ["src/eventstore/ingest.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_ingest.py::"
                "test_a_partially_overlapping_batch_inserts_only_the_new_events"
            ),
            "weight": 5,
            "required": True,
            "description": "Three new events survive a batch whose first two are duplicates",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_ingest.py::test_a_retried_batch_is_absorbed_without_double_counting"
            ),
            "weight": 3,
            "required": True,
            "description": "A fully duplicate batch reports five duplicates, not one",
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
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "The CI pipeline passes, including the re-load smoke test",
        },
        {
            "id": "R5",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, CI, the committed exports and the seed generator are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Read the receipt as the diagnostic it is: one duplicate reported in a "
                "batch with 112 of them means the write stopped at the first error rather "
                "than collecting them all"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Said the loss is recoverable only if the producer can replay, and that "
                "the 202 receipt told the gateway the batch was accepted -- so our "
                "acknowledgement was wrong, not just our write"
            ),
        },
    ],
    "baseline": baseline("ex-034-a-retried-batch-swallowed-nine-hundred-events"),
    "context_excerpts": [
        {
            "path": "src/eventstore/ingest.py",
            "line_range": "1-30",
            "why": (
                "The module docstring, which states both rules the write path is built on: "
                "that deduplication is the index rather than a lookup, and why unordered "
                "matters. The second paragraph describes this exact failure."
            ),
        },
        {
            "path": "ARCHITECTURE.md",
            "line_range": "59-69",
            "why": (
                "'Deduplication is the database's job' -- the design the fix has to "
                "restore, and why the obvious alternative is a race."
            ),
        },
    ],
    "hints": [
        "Run `make test`. Both failures are in `tests/test_ingest.py`; the one about a "
        "partially overlapping batch is the incident reproduced at five events.",
        "Look at the receipt in the ticket again: one duplicate reported, in a batch where "
        "112 events were already present. What kind of write stops counting after the "
        "first error?",
        "`ingest_events` in `src/eventstore/ingest.py` performs one `insert_many`. Read "
        "the module docstring's paragraph headed 'Unordered matters', then look at the "
        "argument actually being passed.",
    ],
    "grading_notes": """\
**Root cause.** `ingest_events` in `src/eventstore/ingest.py` calls `insert_many` with
`ordered=True`. MongoDB stops at the first error in an ordered bulk write, so a retried
batch whose first document is already present inserts nothing after it and reports a
single duplicate. The comment left behind gives an unrelated motivation about the replay
tool's assumptions about natural order.

**The expected fix** is `ordered=False`. One argument.

**This is a beginner-shaped fix with an intermediate-shaped diagnosis**, which is why the
box is 30 minutes rather than 20. Nothing crashes and nothing is logged; the endpoint
returns 202 and a plausible receipt. The route in is the receipt itself.

**S1 is the diagnostic step.** The ticket states `"inserted": 0, "duplicates": 1` for a
batch with 112 known duplicates. That single number is the entire clue: a write that
collected every error would have reported 112, so the write stopped at the first one. A
candidate who says that explicitly found the bug by reasoning rather than by running the
test, and that is the skill the exercise is for.

**S2 is the incident judgement.** The events are gone from our side and are only
recoverable if the producer can replay them — and we returned 202, which told the gateway
the batch was accepted. Our acknowledgement was wrong, not merely our write. A candidate
who notices that the API's contract was also violated is seeing the whole failure.

**Watch for:**

- **Re-implementing deduplication in Python** — querying for existing ids, then inserting
  the remainder. It passes the tests and reintroduces exactly the race the unique index
  exists to prevent: two workers replaying the same batch both see "absent". The module
  docstring and `ARCHITECTURE.md` both say this. Not a hard failure, but it is the wrong
  answer to a question the codebase already answered, and the engineering-quality score
  should reflect that.
- **Inserting one document at a time in a loop** with a try/except per event. Correct
  results, one network round trip per event, and at this service's volume that is the next
  incident. Say so.
- **Using `upsert` / `replace_one`** per document. Same cost problem, and it silently
  overwrites an existing event with a re-delivered copy rather than leaving the original
  alone — which matters, because `received_at` would then move and the rollup's
  ingest-time watermark is built on it.
- **Catching `BulkWriteError` and returning success without counting.** Makes the symptom
  invisible instead of fixing it. If the counts in the receipt are wrong, that is a symptom
  patch; set the flag.
- **Editing the tests.** Protected. Hard F.

**On documentation.** This is a SEV-1 with data loss. A writeup that says "changed ordered
to False" and stops has not done the job. The brief asks how many events were lost and how
to get them back; a good answer also says the loss window is every retried delivery since
the change, which `git log` dates.
""",
}


# ---------------------------------------------------------------------------
# ex-035 -- fix a severe latency issue
# ---------------------------------------------------------------------------

EX035 = {
    "slug": "ex-035-the-recent-events-panel-reads-the-whole-window",
    "exercise_number": 35,
    "title": "The on-call panel times out exactly when somebody needs it",
    "exercise_type": ExerciseType.LATENCY,
    "base_app": BaseApp.EVENTSTORE,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "limit_applied_after_the_fetch",
    "time_limit_minutes": 40,
    "expected_time_minutes": 24,
    "databases": [Database.MONGODB],
    "needs_docker": True,
    "tags": ["mongodb", "indexes", "query-plan", "latency", "explain"],
    "brief_md": """\
## INC-2310 — `/v1/events/recent` is unusable during an incident

**Severity:** SEV-2
**Reported by:** on-call, twice this month

The recent-events panel is what on-call opens first. It asks for the last 100 events for
a service and renders them newest-first. During quiet periods it is instant. During an
incident — when the window is full and somebody widens it to a day to see the shape — it
takes tens of seconds or times out.

The irony is noted in the ticket: it is slowest exactly when it is needed.

### What we know

- **The answer is correct.** 100 events, newest first, correct window. This is a cost
  problem, not a correctness problem.
- The compound index the query was designed around is still there and is still being used
  — `eventstore` creates it on start-up and `make test` confirms it exists.
- `bench/bench_query.py` measures what the server actually had to do, in documents
  examined rather than milliseconds. On a 20,000-event collection a healthy run examines
  **100** documents to return 100.
- One test fails, and it is not a correctness test. It asserts something about the plan.

### Reproducing it

```bash
docker compose up -d --wait
make test
make bench
```

Read the benchmark's output, not just its number: it prints how many events are in the
window alongside how many documents were examined.

### What we need

The query must examine on the order of what it returns, not on the order of what the
window contains. `make bench` must report `docs_examined` well under 500 and the suite
must stay green.

### Watch out for

"It uses the index" is not the same claim as "it is doing the right amount of work", and
the benchmark output distinguishes them. The index is not the problem here.
""",
    "definition_of_done": [
        "R1: tests/test_queries.py::test_the_recent_query_examines_about_what_it_returns passes",
        "R2: bench/bench_query.py reports docs_examined <= 500",
        "R3: the whole suite is green, with no test skipped, deleted or weakened",
        "R4: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md explains why the index was never the problem",
    ],
    "focus_paths": ["src/eventstore/queries.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_queries.py::test_the_recent_query_examines_about_what_it_returns"
            ),
            "weight": 4,
            "required": True,
            "description": "The server examines about as many documents as it returns",
        },
        {
            "id": "R2",
            "kind": CheckKind.BENCHMARK,
            "target": "python bench/bench_query.py --json",
            "expect": {"metric": "docs_examined", "op": "<=", "threshold": 500},
            "weight": 4,
            "required": True,
            "description": (
                "100 on a healthy query against a 4999-event window; 4999 when the limit "
                "is not applied by the server"
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
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, CI, the committed exports and the seed generator are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Separated 'uses an index' from 'does the right amount of work': the plan "
                "was index-served throughout and the cost came from never telling the "
                "server to stop"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Noticed that the comment's justification no longer holds -- the "
                "de-duplication it protected was removed when the unique index landed -- "
                "rather than only deleting the code"
            ),
        },
    ],
    "baseline": baseline("ex-035-the-recent-events-panel-reads-the-whole-window"),
    "context_excerpts": [
        {
            "path": "src/eventstore/queries.py",
            "line_range": "61-104",
            "why": (
                "recent_cursor, which is explicitly the one definition of this query that "
                "both the endpoint and the benchmark use. Its docstring states what the "
                "limit is for in one sentence."
            ),
        },
        {
            "path": "ARCHITECTURE.md",
            "line_range": "6-27",
            "why": (
                "'Two stores, and the line between them', including the rule that a "
                "request handler never scans Mongo -- which is what this endpoint had "
                "started doing."
            ),
        },
    ],
    "hints": [
        "`make bench` prints how many events are in the window next to how many documents "
        "were examined. Compare the two numbers, then compare both against the 100 the "
        "endpoint returns.",
        "The failing test asserts on the execution plan rather than the result. Read what "
        "it is comparing and what its docstring says the ratio means.",
        "`recent_cursor` in `src/eventstore/queries.py` takes a `limit` argument. Follow "
        "it: check whether anything in that function still uses it, and then look at where "
        "the trimming actually happens.",
    ],
    "grading_notes": """\
**Root cause.** `recent_cursor` in `src/eventstore/queries.py` no longer calls `.limit()`,
so the server walks the entire window; `recent_events` slices the materialised list to
`limit` afterwards. The result is correct and the cost is the size of the window. The
comment left behind explains that the trim used to run after a de-duplication pass, which
was removed when the unique index landed — so the justification is stale rather than wrong.

**The expected fix** restores `.limit(limit)` on the cursor. Removing the now-redundant
Python slice is good but not required; leaving it is harmless.

**Measured, on a 20,000-event collection with a one-day window:**

| | events in window | docs examined | returned |
|---|---|---|---|
| fixed | 4999 | **100** | 100 |
| broken | 4999 | **4999** | 4999 |

A factor of fifty, and it grows with traffic — which is why it only hurts during an
incident.

**S1 is the point of the exercise.** Every tempting diagnosis here is wrong in the same
way. The compound index exists. The plan uses it. There is no in-memory sort — the
benchmark prints `sorted in RAM: no` in both states. A candidate who checks those three
things, finds them all healthy, and keeps going is doing the thing that distinguishes a
real latency investigation from index cargo-culting. The cost was never the index; it was
never telling the server to stop.

**S2 rewards reading the comment properly.** It gives a reason that was true once. A
candidate who checks whether the de-duplication still exists — it does not — and says so is
treating code archaeology as evidence rather than as noise.

**Watch for:**

- **Adding another index.** The most common wrong move, and it changes nothing: the
  existing one is already serving the query. If they add one, R1 and R2 still fail, and the
  feedback should say that a benchmark showing an index in use was the evidence against
  this all along.
- **Narrowing the default window** from 1440 minutes, or lowering `MAX_RECENT_MINUTES`.
  This makes the benchmark number smaller without fixing anything, and takes away the
  wide-window view the ticket says on-call needs. If R2 passes this way it is a symptom
  patch: set the flag.
- **Keeping the slice and adding `.limit()` too.** Correct and slightly redundant. Fine;
  mention that the slice is now dead.
- **Moving the limit into an aggregation pipeline with `$limit`.** Works, and is more
  machinery than the problem needs. Accept it, note the simpler fix.
- **"Fixing" `explain_recent` instead** so the plan it reports looks better. That function
  deliberately explains the same cursor the endpoint runs; making it explain a different
  query would hide the problem rather than fix it, and R2 would still fail because the
  benchmark measures the real one. If attempted, that is a clear symptom patch.
- **Editing the test or the benchmark.** `tests/**` is protected; `bench/` is not, so a
  candidate *can* edit the benchmark. R2 runs it regardless, and a benchmark edited to
  report a smaller number is tampering — treat it as such.
""",
}


#: Every eventstore exercise, in catalog order.
EXERCISES: list[dict] = [EX030, EX031, EX032, EX033, EX034, EX035]
