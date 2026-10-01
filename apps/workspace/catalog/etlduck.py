"""Exercises built on the ``etlduck`` base application.

Same ``(base_app, mutations)`` shape as the other catalog modules, and baselines are likewise
**measured** into ``baselines.json`` by the verification harness rather than authored here.

What distinguishes this base app is that most of its defects **conserve the total**. A
pipeline that loses money gets noticed; one that moves money between days, or between
accounts, reconciles perfectly at the month level and is wrong in every report anyone
actually reads. Several exercises here are built on that, which is also why they are the
catalog's advanced tier: the symptom is a shape rather than a number, and finding it means
reasoning across two or three layers.
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


#: The tests are the proof, so editing them is tampering. Two additions specific to this base
#: app: ``raw/**`` because the suite asserts exact totals over those committed files, and
#: ``tools/gen_seed_data.py`` because regenerating the landing zone would change every one of
#: those constants -- making the data fit the code rather than the other way round.
STANDARD_PROTECTED = [
    "tests/**",
    "pyproject.toml",
    "ci/run_ci.sh",
    "ci/pipeline_smoke.sh",
    ".github/workflows/ci.yml",
    "raw/**",
    "tools/gen_seed_data.py",
]

#: Shared context: the paragraph on what UTC normalisation is for and how big the affected
#: slice actually is.
UTC_EXCERPT = {
    "path": "ARCHITECTURE.md",
    "line_range": "67-88",
    "why": (
        "The 'Nothing is guessed' rules, including the measured size of the timezone "
        "problem: 58 of 400 events are close enough to midnight to move. The rule any fix "
        "at this seam is judged against."
    ),
}


# ---------------------------------------------------------------------------
# ex-022 -- build or fix a data/ETL pipeline
# ---------------------------------------------------------------------------

EX022 = {
    "slug": "ex-022-daily-totals-straddle-midnight",
    "exercise_number": 22,
    "title": "Daily revenue is wrong for every day and the monthly total is exactly right",
    "exercise_type": ExerciseType.ETL_PIPELINE,
    "base_app": BaseApp.ETLDUCK,
    "difficulty": Difficulty.ADVANCED,
    "defect_class": "event_date_from_local_not_utc",
    "time_limit_minutes": 45,
    "expected_time_minutes": 28,
    "databases": [Database.DUCKDB],
    "needs_docker": True,
    "tags": ["etl", "duckdb", "medallion", "timezones", "data-quality"],
    "brief_md": """\
## DATA-1180 — the daily usage report disagrees with itself

**Severity:** SEV-2
**Reported by:** Finance, via #data-platform

Finance reconciled the March usage report against the monthly invoice run. **The month
total matches to the cent.** Every individual day in it is wrong.

Two specifics from their note:

- The report shows usage starting on 1 March and ending on 2 March. They know we received
  events either side of that window, because the invoices include them.
- Both days show **exactly 200 events**. Their words: "we have never had two days with
  identical volume, let alone round numbers."

### Reproducing it

```bash
docker compose up -d --wait
make test
make run
etlduck gold && etlduck check
```

The daily shape is the thing to look at. `notebooks/02_validate_gold.py` prints it, and the
section headed "Daily shape" tells you what the correct answer looks like.

### What we know

- **No money is missing.** `gold` sums to the same number of cents it should. Whatever is
  wrong is moving usage between days rather than losing it, which is why the month
  reconciles and why nobody caught this for three weeks.
- `raw/`, the test suite and `tools/gen_seed_data.py` are off limits. The deliveries are
  fine; nothing needs regenerating.
- The upstream sends mixed offsets — `+00:00`, `-05:00`, `+05:30`, `+09:00`, `-08:00`, `Z`.
  That is normal and is not itself the bug.

### Watch out for

A total that reconciles is **not** evidence that a rollup is correct. It is evidence that
nothing was lost. Those are different claims, and only one of them is what Finance asked
about.

`ARCHITECTURE.md` states a rule about where a date may come from and quantifies how many
rows it affects. Quote the number in `NOTES.md`, and say how many cents moved between which
days — Finance will want to know which of their reports to reissue, not that a line changed.
""",
    "definition_of_done": [
        "R1: tests/test_silver_parsing.py::test_event_date_is_always_the_utc_date_of_the_instant passes",
        "R2: tests/test_gold_rollups.py::test_the_committed_data_yields_the_expected_gold passes",
        "R3: tests/test_quality_cli_profile.py::test_the_committed_run_passes_every_quality_gate passes",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md says how many cents moved between which days, and why the month "
        "total reconciled anyway",
    ],
    "focus_paths": ["src/etlduck/silver.py", "src/etlduck/gold.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_silver_parsing.py::test_event_date_is_always_the_utc_date_of_the_instant"
            ),
            "weight": 4,
            "required": True,
            "description": "event_date is the UTC date of the instant, for every row",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_gold_rollups.py::test_the_committed_data_yields_the_expected_gold",
            "weight": 4,
            "required": True,
            "description": (
                "30 gold rows over 4 UTC dates totalling 817691 cents. Pre-fix it is 16 rows "
                "over 2 dates and the same 817691 cents, which is the whole exercise"
            ),
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_quality_cli_profile.py::test_the_committed_run_passes_every_quality_gate"
            ),
            "weight": 3,
            "required": True,
            "description": "dates_are_utc_consistent passes again, along with the other five gates",
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
            "description": "The CI pipeline passes, including the idempotency smoke test",
        },
        {
            "id": "R6",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": (
                "Tests, CI, the committed deliveries and the seed generator are untouched -- "
                "regenerating raw/ would move the constants instead of fixing the code"
            ),
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Explained why the month total reconciled while every day was wrong -- the "
                "defect redistributes rather than loses -- and drew the conclusion that a "
                "reconciling total is not evidence of a correct rollup"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Used the exactly-200-per-day uniformity as the diagnostic it is: a date "
                "taken from the filename's day rather than from the event, because real "
                "usage is never that even"
            ),
        },
    ],
    "baseline": baseline("ex-022-daily-totals-straddle-midnight"),
    "context_excerpts": [
        UTC_EXCERPT,
        {
            "path": "src/etlduck/db.py",
            "line_range": "53-62",
            "why": (
                "The silver_usage schema, where event_date is declared and commented as "
                "'derived from the UTC instant'. The contract the fix has to restore, stated "
                "where the column is defined."
            ),
        },
        {
            "path": "notebooks/02_validate_gold.py",
            "line_range": "63-78",
            "why": (
                "The 'Daily shape' cell, which states that more distinct dates than days of "
                "input is correct and why. A candidate who reads this knows the two-date "
                "output is wrong without needing to run anything."
            ),
        },
    ],
    "hints": [
        "Run `etlduck gold` then look at the daily breakdown -- "
        "`python notebooks/02_validate_gold.py` prints it. Compare the number of distinct "
        "dates against the number of days of deliveries in `raw/`, and read what the "
        "notebook says about which is correct.",
        "`etlduck check` names a gate that is failing. Read what that gate compares, in "
        "`src/etlduck/quality.py` -- it re-derives something rather than trusting it, and "
        "the reason it bothers is in its docstring.",
        "`build_silver` in `src/etlduck/silver.py` writes `event_date` from the raw delivered "
        "timestamp instead of from the UTC instant it just parsed. For an event at "
        "`2026-03-01T23:30:00-05:00` those are different days, and 58 of the 400 events are "
        "close enough to midnight for it to matter.",
    ],
    "grading_notes": """\
**Root cause.** `src/etlduck/silver.py::build_silver` writes `event_date` from
`datetime.fromisoformat(row[3])` -- the raw timestamp exactly as the upstream delivered it,
in whatever offset that was -- instead of from `occurred_at.date()`, the UTC instant parsed
two lines earlier. The comment added alongside it states the rationale out loud: "the date
the customer saw". That is a real thing somebody might want and it is not what this column
is for; `db.py` declares `event_date` as "derived from the UTC instant" and
`dates_are_utc_consistent` exists to check exactly that.

**The expected fix** restores `occurred_at.date()`. One line.

**Measured, and the shape is the point.**

| | gold rows | dates | total cents |
|---|---|---|---|
| fixed | 30 | **4** | 817691 |
| broken | 16 | **2** | 817691 |

The total is **identical**. The money moved:

| date | fixed | broken | difference |
|---|---|---|---|
| 2026-02-28 | 8 events, 16051c | — | the day disappears |
| 2026-03-01 | 179 events, 360702c | 200 events, 412168c | **+51466c, +14.3%** |
| 2026-03-02 | 188 events, 389665c | 200 events, 405523c | **+15858c, +4.1%** |
| 2026-03-03 | 25 events, 51273c | — | the day disappears |

Six tests fail and `dates_are_utc_consistent` is the gate that catches it. Note that the
quarantine counts, the silver row count and the reconciliation are all **unchanged** -- a
candidate checking those will conclude the pipeline is healthy.

**What separates a strong answer.** Two things, and both are about reading evidence rather
than finding a line.

First (S1): the month reconciles because the defect *redistributes* rather than loses. A
total that adds up is evidence nothing was lost, not evidence the rollup is right, and those
are different claims. A candidate who states that has learned the transferable thing.

Second (S2): the broken output is exactly 200 events on each of two days. That uniformity is
the diagnostic -- it is the signature of a date taken from the delivery's filename day rather
than from the event, because real usage is never that even. Finance spotted it before we did,
which is in the brief on purpose.

The brief also asks which reports to reissue. The answer is both days, and 1 March is the
badly wrong one at +14%; 2 March is +4%. A writeup that gives those numbers is doing the job
the incident actually created.

**Common wrong turns.**

- *Fixed `quality.check_dates_are_utc_consistent`* so it compares the local date instead. The
  gate then passes and the warehouse stays wrong. R1 and R2 catch it. This is the most
  tempting wrong move because the gate is what is shouting, and it is worth saying in feedback
  that a check which fails is doing its job.
- *Re-derived `event_date` in `gold.py`* from `occurred_at` while leaving silver wrong. Gold
  is then right and silver still disagrees with itself, so R1 fails. Partial credit: the
  instinct to fix it at the layer that owns the column is right, they just picked the wrong
  layer. `db.py` says which one owns it.
- *Converted the raw timestamp to UTC and then took the date of that*, which is the same thing
  as the correct fix written the long way round. Fully correct; do not mark it down for not
  being the one-liner, but note that `occurred_at` already holds exactly that value.
- *Regenerated `raw/` or edited the tests* so the new numbers are "expected". Both protected.
  Hard F, and the clearest possible example of making the data fit the code.
- *Concluded the mixed offsets upstream are the problem* and proposed asking the producer to
  send UTC only. Reasonable instinct, wrong conclusion: the brief says the mixed offsets are
  normal, and the pipeline's whole design is built to handle them. Worth engaging with in
  feedback rather than just marking down -- the candidate has understood the mechanism and
  drawn a conclusion one step too far.

**On documentation.** This is a one-line fix with a three-paragraph explanation behind it, so
the writeup carries most of the grade. A strong `NOTES.md` quotes the 58-of-400 figure from
`ARCHITECTURE.md`, gives the per-day cent movements, explains the conserved total, and tells
Finance which reports to reissue. One that says "event_date now uses the UTC instant" is
correct and worth a C+.
""",
}


# ---------------------------------------------------------------------------
# ex-023 -- build or fix a data/ETL pipeline
# ---------------------------------------------------------------------------

EX023 = {
    "slug": "ex-023-gold-build-fails-on-a-duplicate-key",
    "exercise_number": 23,
    "title": "The gold job has failed every night since Tuesday with a duplicate key",
    "exercise_type": ExerciseType.ETL_PIPELINE,
    "base_app": BaseApp.ETLDUCK,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "dimension_join_fans_out",
    "time_limit_minutes": 35,
    "expected_time_minutes": 22,
    "databases": [Database.DUCKDB],
    "needs_docker": True,
    "tags": ["etl", "duckdb", "sql", "joins", "dimensions"],
    "brief_md": """\
## DATA-1206 — gold has not built since Tuesday

**Severity:** SEV-2
**Reported by:** the nightly job, five times in a row

```
_duckdb.ConstraintException: Constraint Error: PRIMARY KEY or UNIQUE constraint
violation: duplicate key "2026-02-28, acct-000"
```

`etlduck gold` exits 1. Bronze and silver still build fine, so the warehouse has current
usage data and a gold table five days stale. Every dashboard downstream is reading Monday.

### Reproducing it

```bash
docker compose up -d --wait
etlduck bronze && etlduck silver   # both fine
etlduck gold                       # the failure above
make test
```

### What we know

- Tuesday's change was to the gold rollup. It was described as a simplification and no
  behaviour change was expected.
- The account dimension arrived in a second delivery around the same time — `accounts.csv`
  and `accounts_delta.csv` are both in `raw/`, and both are supposed to be there.
- Nothing is wrong with silver. `etlduck silver` reports its usual 400 rows.

### Watch out for

The error names a `(date, account)` pair, and that pair is the **primary key of
`gold_daily_usage`**. So the question is not "why is this one account special" — it is
**how a rollup grouped by (date, account) can produce the same pair twice**. Work that out
before changing anything; the answer tells you which table is the problem, and it is not
the one in the error message.

`ARCHITECTURE.md` has a section devoted to this failure. Read it, and in `NOTES.md` say
what the primary key did for us here — the answer is not "it broke the job".
""",
    "definition_of_done": [
        "R1: etlduck run exits 0 -- the pipeline completes end to end",
        "R2: tests/test_gold_rollups.py::test_a_redelivered_account_does_not_double_its_usage passes",
        "R3: tests/test_gold_rollups.py::test_the_latest_delivery_supplies_the_plan passes",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md says what the primary key protected us from, not just what it blocked",
    ],
    "focus_paths": ["src/etlduck/gold.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.CMD,
            "target": "etlduck run",
            "expect": {"exit_code": 0},
            "weight": 4,
            "required": True,
            "description": (
                "The pipeline completes end to end. `etlduck run` rather than `etlduck gold`: "
                "a freshly scaffolded warehouse is empty, so the rollup alone inserts nothing "
                "and exits 0 whether or not the join fans out"
            ),
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_gold_rollups.py::test_a_redelivered_account_does_not_double_its_usage"
            ),
            "weight": 4,
            "required": True,
            "description": (
                "One event of 500 cents for a twice-delivered account stays 500 cents. The "
                "test that states the property rather than the symptom"
            ),
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_gold_rollups.py::test_the_latest_delivery_supplies_the_plan",
            "weight": 3,
            "required": True,
            "description": (
                "Collapsing the dimension is not enough: the row kept has to be the latest "
                "delivery, so an upgraded account reports its new plan"
            ),
        },
        {
            "id": "R4",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": (
                "No regressions. Weighted because a third of the suite cannot even run "
                "pre-fix: its fixture builds gold, and gold raises"
            ),
        },
        {
            "id": "R5",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "The CI pipeline passes, including the idempotency smoke test",
        },
        {
            "id": "R6",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, CI, the committed deliveries and the seed generator are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Worked out that the primary key is what saved them: without the constraint "
                "the fan-out would have silently doubled two accounts' revenue and only the "
                "reconciliation would have caught it, after the numbers had shipped"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Noticed that LATEST_ACCOUNTS_SQL was still defined directly above the "
                "rollup, unused -- the deduplicating view the join used to go through"
            ),
        },
    ],
    "baseline": baseline("ex-023-gold-build-fails-on-a-duplicate-key"),
    "context_excerpts": [
        {
            "path": "ARCHITECTURE.md",
            "line_range": "52-66",
            "why": (
                "The section titled 'The fan-out, which is the easiest way to inflate "
                "revenue', which explains the mechanism and states that the committed data "
                "contains the case on purpose. The authority the fix is judged against."
            ),
        },
        {
            "path": "src/etlduck/db.py",
            "line_range": "72-80",
            "why": (
                "The gold_daily_usage schema, where the primary key on (event_date, "
                "account_id) is declared. Needed to judge whether the candidate understood "
                "the constraint as a guard rather than an obstacle."
            ),
        },
    ],
    "hints": [
        "The error names the primary key of `gold_daily_usage`. Ask how a query that groups "
        "by `(event_date, account_id)` can emit that pair twice -- the GROUP BY has a third "
        "column in it, and that is where to start.",
        "Count the rows in `bronze_accounts` and compare that against the number of distinct "
        "`account_id` values. The dimension holds one row per *delivery*, not one per "
        "account, and two accounts were re-delivered with a different plan.",
        "`ROLLUP_SQL` in `src/etlduck/gold.py` joins `bronze_accounts` directly. It should "
        "join `LATEST_ACCOUNTS_SQL`, the deduplicating view defined immediately above it and "
        "currently unused.",
    ],
    "grading_notes": """\
**Root cause.** `src/etlduck/gold.py::ROLLUP_SQL` joins `bronze_accounts` directly instead of
the `LATEST_ACCOUNTS_SQL` view. `bronze_accounts` holds **one row per delivery**: 10 rows for
8 accounts, because `accounts_delta.csv` re-delivers `acct-000` and `acct-001` with an
upgraded plan. The join therefore emits one row per (usage event x delivery), and because the
`GROUP BY` includes `a.plan` -- which differs between the two deliveries -- each affected
account gets **two** rows per date, one per plan.

**The expected fix** restores the join through `LATEST_ACCOUNTS_SQL`. One line.

**Measured.** `etlduck gold` exits 1 with
`duplicate key "2026-02-28, acct-000"`. Two tests fail by name and **fourteen more error**,
because their fixture builds gold and gold raises. That is not a mutation that broke more
than intended -- it is what a pipeline whose third layer cannot build actually looks like, and
the two named failures point at the cause precisely.

The dimension state behind it:

```
bronze_accounts rows: 10
distinct accounts   : 8
  acct-000: 2 deliveries, plans free/enterprise
  acct-001: 2 deliveries, plans team/enterprise
```

**The most valuable thing here is the thing that did not happen.** Had the two deliveries
carried the *same* plan, the `GROUP BY` would have collapsed them into one row with doubled
counts, the primary key would have been satisfied, and gold would have shipped two accounts'
revenue at double. Nothing would have raised; only `gold_reconciles_with_silver` would have
noticed, and only after the numbers were in a dashboard. The constraint turned a silent
inflation into a loud failure, which is the whole argument for constraining the grain. S1 is
the check for whether the candidate got there, and it is weighted 2 because it is the
transferable lesson rather than the fix.

**Two parts to a correct fix, and R3 is why.** Collapsing the dimension is necessary but not
sufficient: the row that survives has to be the **latest** delivery, or an upgraded account
keeps reporting its old plan. `LATEST_ACCOUNTS_SQL` orders by `ingested_at DESC` then
`source_file` then `rowid` for exactly that, and the tie-breaks matter because two files can
land in the same second.

**Common wrong turns.**

- *Dropped the primary key* from `gold_daily_usage`, or switched the insert to
  `INSERT OR REPLACE`. The job then succeeds and ships doubled revenue for two accounts. R2
  catches it and `gold_reconciles_with_silver` would too. This is the single worst outcome
  available and should be graded as such: it removes the guard that caught the bug, in
  response to the guard catching the bug. Cap correctness around 40 and set
  `symptom_patch_suspected`.
- *Added `DISTINCT` to the select*, or `GROUP BY` without `a.plan`. Dropping `plan` from the
  grouping makes the key unique again and then picks an arbitrary plan per account -- which is
  nondeterministic across runs and silently wrong for the upgraded accounts. R3 catches it.
  Correctness around 60; explain that it trades a loud failure for an arbitrary answer.
- *Deduplicated `bronze_accounts` in place*, deleting the older rows. Gold builds and the
  tests pass, but bronze is supposed to be a verbatim record of what arrived -- the layer's
  entire purpose -- and the next delivery re-creates the problem. Correctness full,
  engineering around 50, and point at the bronze contract in `ARCHITECTURE.md`.
- *Blamed the second delivery* and proposed asking upstream to send full snapshots only. The
  brief says both files are supposed to be there, and handling re-delivery is what the
  dimension logic is for. Worth engaging with rather than dismissing: the candidate has
  understood the mechanism and drawn the conclusion one step too far.
- *Edited the tests, CI, `raw/` or the generator.* All protected. Hard F.

**On documentation.** The brief asks what the primary key did for us. A strong `NOTES.md`
answers that it converted a silent double-count into a failed job, names the two affected
accounts and why their differing plans are what triggered the key rather than the doubling
itself, and notes that `LATEST_ACCOUNTS_SQL` was sitting right there unused. "Joined the
deduplicated view instead" is correct and worth a C+.
""",
}


# ---------------------------------------------------------------------------
# ex-024 -- build or fix a data/ETL pipeline
# ---------------------------------------------------------------------------

#: Proves the property behaviourally rather than by reading code: build a landing zone whose
#: dimension is truncated, run the pipeline, and require the watermark to have held. Pre-fix
#: it advances to 2026-03-02T06:54:27Z over a batch that failed; post-fix it stays at the
#: epoch. Runs in a scratch directory so the candidate's own warehouse is untouched.
WATERMARK_HOLDS_PROBE = r"""d=$(mktemp -d); mkdir -p "$d/raw" "$d/warehouse"
python - "$d" <<'PY'
import shutil
import sys
from pathlib import Path

from etlduck import connect, run_pipeline
from etlduck.pipeline import USAGE_STREAM
from etlduck.watermark import EPOCH, get_watermark

scratch = Path(sys.argv[1])
scratch.joinpath("raw", "accounts.csv").write_text(
    "account_id,name,plan,country\n"
    + "".join(f"acct-{n:03d},A{n},team,DE\n" for n in range(3))
)
shutil.copy2("raw/usage_events_2026-03-01.jsonl", scratch / "raw")
connection = connect(scratch)
try:
    result = run_pipeline(connection, scratch, strict=False)
    assert not result.ok, "the probe batch was meant to fail its quality gates"
    mark = get_watermark(connection, USAGE_STREAM)
finally:
    connection.close()
assert mark == EPOCH, f"watermark advanced to {mark.isoformat()} over a batch that failed"
print("ok: the watermark held")
PY
"""

EX024 = {
    "slug": "ex-024-a-failed-batch-was-marked-processed",
    "exercise_number": 24,
    "title": "Thursday's usage is missing and no job has failed since",
    "exercise_type": ExerciseType.ETL_PIPELINE,
    "base_app": BaseApp.ETLDUCK,
    "difficulty": Difficulty.ADVANCED,
    "defect_class": "watermark_advanced_before_the_gates",
    "time_limit_minutes": 40,
    "expected_time_minutes": 25,
    "databases": [Database.DUCKDB],
    "needs_docker": True,
    "tags": ["etl", "duckdb", "watermarks", "incremental", "idempotency"],
    "brief_md": """\
## DATA-1241 — a day of usage is missing and nothing is failing

**Severity:** SEV-2
**Reported by:** Finance, reconciling the month

Thursday's usage is absent from gold. There is no gap in `raw/` — the deliveries are
there — and no job has reported a failure since.

What we can reconstruct from the logs:

- Thursday's run **did** fail. The accounts export arrived truncated, the
  `accounts_present` gate tripped, and the job exited non-zero. That is the gate working.
- Somebody re-ran it on Friday with the full dimension. It succeeded.
- Thursday's usage is still missing, and every run since has succeeded while continuing
  not to process it.

That last point is the one to explain. A failed batch followed by a successful re-run
should leave nothing behind.

### Reproducing it

```bash
docker compose up -d --wait
make test
```

Two tests fail and both name the property. A healthy run is entirely unaffected — `make
run` against the committed deliveries works and reports the watermark you would expect —
so there is nothing to see until you make a batch fail on purpose. The two failing tests
show you how; `test_a_run_that_fails_its_quality_gates_does_not_advance_the_watermark`
constructs exactly the Thursday scenario in six lines.

### What we know

- The quality gates are fine. `accounts_present` tripped when it should have.
- `advance_watermark` refuses to move backwards, and that still works.
- `raw/`, the tests, CI and the seed generator are off limits.

### Watch out for

Work out **why re-running did not fix it.** A re-run that reprocesses the window is a
normal recovery; this one succeeded and still skipped the window, which means the pipeline
believes Thursday is done. Find what told it that.

`ARCHITECTURE.md` has a section on watermarks that states two rules and explains why one of
the two failure modes never heals on its own. In `NOTES.md`, say which of the two happened
here and why no amount of re-running would have recovered it.
""",
    "definition_of_done": [
        "R1: a run whose quality gates fail leaves the watermark where it was",
        "R2: tests/test_watermark.py::"
        "test_a_run_that_fails_its_quality_gates_does_not_advance_the_watermark passes",
        "R3: tests/test_watermark.py::test_a_non_strict_run_still_refuses_to_advance passes",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md says why re-running could never have recovered Thursday",
    ],
    "focus_paths": ["src/etlduck/pipeline.py", "src/etlduck/watermark.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.CMD,
            "target": WATERMARK_HOLDS_PROBE,
            "expect": {"exit_code": 0},
            "weight": 5,
            "required": True,
            "description": (
                "The property itself, proved behaviourally: a batch with a truncated "
                "dimension fails its gates and the watermark must still be at the epoch. "
                "Pre-fix it advances to 2026-03-02T06:54:27Z"
            ),
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_watermark.py::"
                "test_a_run_that_fails_its_quality_gates_does_not_advance_the_watermark"
            ),
            "weight": 4,
            "required": True,
            "description": "The gate protects the watermark, not the other way round",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_watermark.py::test_a_non_strict_run_still_refuses_to_advance",
            "weight": 3,
            "required": True,
            "description": (
                "strict=False changes whether a failing gate shouts, never whether the "
                "watermark moves -- so the flag cannot be used to get past the gate"
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
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, CI, the committed deliveries and the seed generator are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Named the asymmetry: a watermark that regresses causes a window to be "
                "re-read, which is wasteful and self-correcting, while one that advances "
                "over failed work skips that window permanently -- which is why re-running "
                "recovered nothing"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Engaged with the rationale in the comment -- avoiding a re-read caused by a "
                "slow quality run -- and said why it does not justify the ordering, or what "
                "would address it instead"
            ),
        },
    ],
    "baseline": baseline("ex-024-a-failed-batch-was-marked-processed"),
    "context_excerpts": [
        {
            "path": "ARCHITECTURE.md",
            "line_range": "105-123",
            "why": (
                "The watermarks section, which states both rules and explains that an "
                "over-advanced watermark never heals because the pipeline is from then on "
                "consistently looking past the window. The authority for the fix and the "
                "answer the writeup is asked for."
            ),
        },
        {
            "path": "src/etlduck/watermark.py",
            "line_range": "94-113",
            "why": (
                "watermark_advanced_on_success, whose docstring says the body runs first and "
                "why. The helper is correct and unmodified -- needed so the candidate's fix "
                "is judged at the call site rather than here."
            ),
        },
    ],
    "hints": [
        "Read the two failing tests before anything else. Both construct a run whose quality "
        "gates fail and then assert something about the watermark; the assertion tells you "
        "the contract that is being broken.",
        "Look at the order of operations in `run_pipeline` in `src/etlduck/pipeline.py`. Three "
        "things happen after gold is built -- the gates run, the result is inspected, and the "
        "watermark moves -- and one of them is in the wrong place.",
        "The watermark is advanced *before* `quality.run_all`, so a batch that fails its gates "
        "is still recorded as processed. It has to move only after the checks pass, which is "
        "where it was and what the comment above it argues against.",
    ],
    "grading_notes": """\
**Root cause.** `src/etlduck/pipeline.py::run_pipeline` advances the watermark immediately
after `build_gold`, **before** `quality.run_all`. A batch that fails its gates is therefore
recorded as processed. The next run reads from after that position, so the failed window is
never looked at again -- and because every subsequent run also starts after it, no amount of
re-running recovers it.

The comment added above the move states the rationale: avoid a slow quality run leaving the
watermark behind and causing a re-read. That is a real concern with a wrong answer; a re-read
is wasteful and self-correcting, which is not the same kind of problem as data that is
skipped permanently.

**The expected fix** moves the watermark back below the gate check. Three lines.

**Measured.** Two tests fail -- both watermark-ordering tests -- and 134 pass. A **healthy
run is completely unaffected**: `etlduck run` against the committed deliveries exits 0 and
reports the same watermark either way, because the committed data passes every gate. So there
is nothing to observe until a batch is made to fail, which is exactly why this reached
production and why the brief has to describe the incident rather than hand over a symptom.

The probe in R1 constructs it: a landing zone with a three-account dimension trips
`accounts_present`, and on the broken pipeline the watermark advances to
**2026-03-02T06:54:27Z** over a batch that failed. On the fixed pipeline it stays at the
epoch.

**What separates a strong answer (S1).** The asymmetry between the two watermark failure
modes, which `ARCHITECTURE.md` states and the brief asks for:

- A watermark that **regresses** makes the next run re-read a window it already processed.
  Wasteful, and self-correcting -- the data ends up right.
- A watermark that **advances over failed work** skips that window, and keeps skipping it,
  because the pipeline is from then on consistently looking past it. Nothing re-reads it,
  nothing fails, and the only evidence is a thin day in a report weeks later.

A candidate who explains that has answered why Friday's successful re-run recovered nothing,
which is the question Finance actually asked. One who fixes the ordering without it has
restored the behaviour and not demonstrated understanding the incident required.

**Common wrong turns.**

- *Fixed it inside `watermark_advanced_on_success`* by reordering the `yield`. That helper is
  already correct and its docstring says the body runs first; the body here is `pass`, so
  reordering it changes nothing and both tests still fail. A candidate who tries this and
  then reads the call site has done reasonable work; one who claims it as the fix has not
  verified anything.
- *Made the watermark conditional on `strict`* -- advancing when `strict=False`. R3 is
  precisely this: the flag decides whether a failing gate raises, never whether work counts
  as processed. Correctness around 50 and explain that it turns a diagnostic flag into a way
  past the gate.
- *Wrapped the gates inside the `with` block* so an assertion failure prevents the advance.
  This actually works for `strict=True` and silently fails for `strict=False`, where
  `assert_ok` is never called and nothing raises. R3 catches it. Partial credit: the instinct
  to use the context manager's contract is good, the coverage is incomplete.
- *Deleted the watermark advance entirely.* Both tests pass and the pipeline reprocesses
  everything every run, which is correct-but-useless and discards the feature. R4 stays green,
  so read the diff: correctness around 60, engineering lower, and note that incremental state
  has a purpose.
- *Blamed the truncated accounts export* and proposed validating the dimension before
  ingesting. A good idea and not this bug -- the gate already caught the bad delivery. The
  failure is what the pipeline did *after* the gate fired.
- *Edited the tests, CI, `raw/` or the generator.* All protected. Hard F.

**On documentation.** The brief asks one specific question: why re-running could never have
recovered Thursday. A strong `NOTES.md` answers it with the asymmetry, names the position the
watermark wrongly moved to, and engages with the stated rationale instead of deleting the
comment. "Moved the watermark after the checks" is correct and worth a C+.
""",
}


# ---------------------------------------------------------------------------
# ex-025 -- build or fix a data/ETL pipeline
# ---------------------------------------------------------------------------

#: Proves the property behaviourally: deliver a file with a wrong amount, re-deliver the same
#: window corrected, and require the correction to be in bronze. Pre-fix bronze holds only the
#: wrong value and the second delivery is discarded as "already loaded". Runs in a scratch
#: directory, so the candidate's own warehouse and the committed deliveries are untouched.
CORRECTION_LANDS_PROBE = r"""d=$(mktemp -d); mkdir -p "$d/raw" "$d/warehouse"
python - "$d" <<'PY'
import json
import sys
from pathlib import Path

from etlduck import connect, table_count
from etlduck.bronze import ingest_all

scratch = Path(sys.argv[1])
raw = scratch / "raw"
raw.joinpath("accounts.csv").write_text(
    "account_id,name,plan,country\n"
    + "".join(f"acct-{n:03d},A{n},team,DE\n" for n in range(6))
)
name = "usage_events_2026-03-01.jsonl"


def event(amount: str) -> str:
    return json.dumps(
        {
            "event_id": "evt-1",
            "account_id": "acct-000",
            "event_type": "api_call",
            "occurred_at": "2026-03-01T10:00:00+00:00",
            "quantity": "1",
            "amount_cents": amount,
        }
    )


raw.joinpath(name).write_text(event("999999") + "\n")
connection = connect(scratch)
try:
    ingest_all(connection, scratch)
    raw.joinpath(name).write_text(event("500") + "\n")
    ingest_all(connection, scratch)
    rows = connection.execute(
        "SELECT amount_cents_raw FROM bronze_usage ORDER BY ingested_at"
    ).fetchall()
    loads = table_count(connection, "load_log")
finally:
    connection.close()

amounts = [r[0] for r in rows]
assert "500" in amounts, (
    f"the corrected re-delivery never landed: bronze holds {amounts}, load_log has {loads} rows"
)
print(f"ok: the correction landed, bronze holds {amounts}")
PY
"""

EX025 = {
    "slug": "ex-025-the-corrected-export-never-landed",
    "exercise_number": 25,
    "title": "Upstream re-issued a corrected export and the bad numbers are still there",
    "exercise_type": ExerciseType.ETL_PIPELINE,
    "base_app": BaseApp.ETLDUCK,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "load_log_keyed_on_filename_only",
    "time_limit_minutes": 30,
    "expected_time_minutes": 18,
    "databases": [Database.DUCKDB],
    "needs_docker": True,
    "tags": ["etl", "duckdb", "idempotency", "hashing", "data-quality"],
    "brief_md": """\
## DATA-1263 — a corrected delivery was ignored

**Severity:** SEV-2
**Reported by:** the upstream metering team

They shipped a usage export last Tuesday with the amounts in the wrong units. They noticed
within the hour, fixed it, and re-dropped the **same window under the same filename** —
which is their documented recovery procedure and has always worked.

Nine days later our warehouse still has their first numbers. The job that was supposed to
pick up the correction has run every night since and reported success every time.

### Reproducing it

```bash
docker compose up -d --wait
make test
```

Two tests fail and both name the property. A first load is unaffected, and so is a re-run
over unchanged files — which is why nothing looked wrong. To see it, you need a file whose
**contents** change while its name does not;
`test_a_file_re_exported_with_new_content_is_loaded_again` builds exactly that in four
lines.

### What we know

- The re-delivery is in `raw/` and `etlduck bronze` reports it as already loaded.
- Nothing is duplicated. Re-running over unchanged files still inserts nothing, which is
  the behaviour we want and is not what broke.
- `raw/`, the tests, CI and the seed generator are off limits.

### Watch out for

This layer has to get **two** things right at once and they pull in opposite directions: a
byte-identical re-delivery must be skipped, and a corrected re-delivery under the same name
must be loaded. A change that fixes one by breaking the other is not a fix — it swaps silent
staleness for silent duplication, which is harder to detect and worse to clean up.

`ARCHITECTURE.md` has a table of the three idempotency mechanisms and says what breaks each
one. In `NOTES.md`, say what the load log is keyed on and why **both** halves of that key
are load-bearing.
""",
    "definition_of_done": [
        "R1: a re-delivery with corrected contents under the same filename is loaded",
        "R2: tests/test_bronze_idempotency.py::"
        "test_a_file_re_exported_with_new_content_is_loaded_again passes",
        "R3: tests/test_bronze_idempotency.py::test_already_loaded_is_keyed_on_name_and_hash passes",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md says why both halves of the load-log key are load-bearing",
    ],
    "focus_paths": ["src/etlduck/bronze.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.CMD,
            "target": CORRECTION_LANDS_PROBE,
            "expect": {"exit_code": 0},
            "weight": 5,
            "required": True,
            "description": (
                "The property, proved behaviourally: a corrected re-delivery lands. Pre-fix "
                "bronze keeps only the wrong amount and discards the correction"
            ),
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_bronze_idempotency.py::"
                "test_a_file_re_exported_with_new_content_is_loaded_again"
            ),
            "weight": 4,
            "required": True,
            "description": "Changed content under an unchanged name is a new delivery",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_bronze_idempotency.py::test_already_loaded_is_keyed_on_name_and_hash"
            ),
            "weight": 3,
            "required": True,
            "description": (
                "The key is the pair. Neither half alone identifies a delivery, and this test "
                "checks both directions"
            ),
        },
        {
            "id": "R4",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": (
                "No regressions -- and specifically that the other half of idempotency still "
                "holds: re-running over unchanged files must still insert nothing"
            ),
        },
        {
            "id": "R5",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "The CI pipeline passes, including the idempotency smoke test",
        },
        {
            "id": "R6",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, CI, the committed deliveries and the seed generator are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Named the inverse hazard as well: keying on a modification time instead "
                "would reload a byte-identical re-delivery and duplicate it, so the content "
                "hash is the only key that is safe in both directions"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Engaged with the stated rationale -- that hashing is work worth skipping -- "
                "rather than ignoring it: the hash is read in chunks, is cheap next to the "
                "insert, and buys the only thing that distinguishes two deliveries"
            ),
        },
    ],
    "baseline": baseline("ex-025-the-corrected-export-never-landed"),
    "context_excerpts": [
        {
            "path": "ARCHITECTURE.md",
            "line_range": "37-51",
            "why": (
                "The 'Idempotency, three different ways' table, which names what breaks each "
                "mechanism -- including 'keying on the filename alone' for bronze. The "
                "authority for the fix, and the paragraph that states both hazards."
            ),
        },
        {
            "path": "src/etlduck/bronze.py",
            "line_range": "45-58",
            "why": (
                "content_hash, whose docstring says why SHA-256 of the bytes rather than a "
                "modification time, in both directions. It is unmodified, so the candidate's "
                "fix is judged at the lookup rather than here."
            ),
        },
    ],
    "hints": [
        "Read the two failing tests. Both are about a file whose name stays the same while "
        "its contents change, which is the upstream's documented recovery procedure and the "
        "case that is now broken.",
        "`load_usage_file` in `src/etlduck/bronze.py` asks `already_loaded` whether to skip. "
        "Look at what that function compares against `load_log`, and then at what the table's "
        "primary key actually is.",
        "`already_loaded` matches on `source_file` alone; the `load_log` primary key is "
        "`(source_file, content_hash)`. The hash is computed a few lines above and then not "
        "used in the comparison.",
    ],
    "grading_notes": """\
**Root cause.** `src/etlduck/bronze.py::already_loaded` matches `load_log` on `source_file`
alone. `content_hash` is still computed in `load_usage_file` and still written to the log --
it is simply not consulted -- so any second delivery under a known filename is discarded
whatever its contents. The comment added alongside states the rationale: one name is one
delivery, so hashing to compare is work worth skipping.

**The expected fix** restores the hash to the comparison. Two lines.

**Measured.** Exactly 2 tests fail, 134 pass. The committed data is **unaffected**: a first
load works and a re-run over unchanged files still skips, which is why nothing looked wrong
for nine days. The probe in R1 shows the real behaviour -- deliver `999999`, re-deliver the
same window corrected to `500`, and bronze holds `['999999']` with the correction silently
dropped. Fixed, it holds `['999999', '500']` and silver's deduplication keeps the later one.

**The thing to grade on.** This layer has two obligations that pull in opposite directions,
and `ARCHITECTURE.md` states both:

- a **byte-identical** re-delivery must be skipped, or a retry duplicates the warehouse;
- a **corrected** re-delivery under the same name must be loaded, or a fix never lands.

The content hash is the only key that satisfies both. Keying on the filename alone fails the
second; keying on a modification time instead would fail the first, because a re-export of
identical bytes gets a new mtime and would be loaded again. S1 is whether the candidate
names that second hazard unprompted — it is the difference between fixing this bug and
understanding why the key is a pair.

**Common wrong turns.**

- *Removed the `already_loaded` check entirely.* The correction lands, R1 and R2 pass, and
  every retry now duplicates everything. `test_loading_the_same_file_twice_inserts_nothing_the_second_time`
  and the CI idempotency smoke test both catch it, which is what R4 and R5 are for. This is
  the trade the brief warns about by name: silent staleness swapped for silent duplication.
  Cap correctness around 45 and set `symptom_patch_suspected`.
- *Keyed on the file's modification time* or its size. Both pass the two named tests and both
  reintroduce duplication on a byte-identical re-delivery — size especially, since a
  corrected amount of the same width changes nothing. Correctness around 60; explain which
  direction they have just broken.
- *Deleted the earlier rows* for that filename before inserting, making the load a replace.
  Defensible on its own terms and wrong for this layer: bronze is a verbatim record of what
  arrived, and the first delivery really did arrive. Silver already resolves the duplicate by
  keeping the latest, which is where that decision belongs. Correctness full, engineering
  around 55, and point at the bronze contract.
- *Added a `--force` flag* to re-ingest. Leaves the default broken and makes recovery a
  manual step somebody has to know about. R1 fails unless the default changed.
- *Edited the tests, CI, `raw/` or the generator.* All protected. Hard F.

**On documentation.** The brief asks why both halves of the key matter. A strong `NOTES.md`
answers with both hazards, notes that the hash was already being computed and merely
unused, and ideally observes that silver's deduplication is what makes loading the
correction safe rather than confusing. "Added the content hash back to the lookup" is
correct and worth a C+.
""",
}


# ---------------------------------------------------------------------------
# ex-026 -- build or fix a data/ETL pipeline
# ---------------------------------------------------------------------------

EX026 = {
    "slug": "ex-026-the-quarantine-rate-has-been-zero-all-month",
    "exercise_number": 26,
    "title": "Our reject rate has been exactly 0.00% for a month and a customer found the gap",
    "exercise_type": ExerciseType.ETL_PIPELINE,
    "base_app": BaseApp.ETLDUCK,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "rejected_rows_dropped_without_a_record",
    "time_limit_minutes": 30,
    "expected_time_minutes": 18,
    "databases": [Database.DUCKDB],
    "needs_docker": True,
    "tags": ["etl", "duckdb", "observability", "data-quality", "quarantine"],
    "brief_md": """\
## DATA-1288 — we cannot tell how much data we are dropping

**Severity:** SEV-3
**Reported by:** a customer, which is the problem

A customer asked why three days of their API usage was missing. It was missing because
their exporter had started sending `amount_cents` with a decimal point, and we reject
those rows. That is the correct behaviour.

What is not correct is that **we had no idea.** Our pipeline has reported a rejection rate
of exactly `0.00%` every night for a month, the quarantine table is empty, and the quality
gate that exists to catch precisely this — an upstream changing its format — has passed
every single run.

### Reproducing it

```bash
docker compose up -d --wait
make test
etlduck run --json
```

Look at what the run reports against what the warehouse contains. The committed deliveries
include ten rows that *should* be rejected, five per day, one of each kind.

### What we know

- **No money is missing.** Silver holds the rows it should and the cent total is right.
  The rows being lost were never valid, so the totals are unaffected — what we have lost
  is the *record* that they arrived.
- `etlduck check` passes. So does CI's quality step.
- `raw/`, the tests, CI and the seed generator are off limits.

### Watch out for

The thing to be angry about here is not the ten rows. It is that the gate designed to warn
us about an upstream format change **cannot fire any more**, so the pipeline's own report
of its health has become unfalsifiable. Work out why it cannot fire, and say so in
`NOTES.md`.

`ARCHITECTURE.md` explains why the quarantine budget is deliberately not zero. That
reasoning only holds if the number means something.
""",
    "definition_of_done": [
        "R1: etlduck run --json reports 10 quarantined rows for the committed deliveries",
        "R2: tests/test_silver_parsing.py::test_a_rejected_row_is_quarantined_with_its_reason passes",
        "R3: tests/test_silver_parsing.py::"
        "test_every_quarantine_reason_is_exercised_by_the_committed_data passes",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md explains why the quarantine budget gate could no longer fire",
    ],
    "focus_paths": ["src/etlduck/silver.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.METRIC,
            "target": "etlduck run --json",
            "expect": {"metric": "quarantined", "op": "==", "threshold": 10},
            "weight": 5,
            "required": True,
            "description": (
                "The run reports the ten rejections the committed data contains. Pre-fix it "
                "reports 0 and still says checks_passed: true"
            ),
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_silver_parsing.py::test_a_rejected_row_is_quarantined_with_its_reason"
            ),
            "weight": 4,
            "required": True,
            "description": "A rejected row lands in quarantine with the rule it broke",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_silver_parsing.py::"
                "test_every_quarantine_reason_is_exercised_by_the_committed_data"
            ),
            "weight": 3,
            "required": True,
            "description": (
                "All five reasons are counted, two of each. A fix that records a count but "
                "loses the reason would pass R1 and fail here"
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
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, CI, the committed deliveries and the seed generator are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Explained that the budget gate computes its rate from the quarantine table, "
                "so a pipeline that records nothing always reports 0% and the gate becomes "
                "structurally unable to fail -- the pipeline's self-reported health turned "
                "unfalsifiable"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Engaged with the rationale -- 'a table nobody reads' -- rather than deleting "
                "the comment: the payload is what lets someone reconstruct what the producer "
                "actually sent, which is the only way to tell a format change from a bad day"
            ),
        },
    ],
    "baseline": baseline("ex-026-the-quarantine-rate-has-been-zero-all-month"),
    "context_excerpts": [
        {
            "path": "src/etlduck/quality.py",
            "line_range": "63-81",
            "why": (
                "check_quarantine_within_budget, which computes its rate from the quarantine "
                "table. It is correct and unmodified; seeing it is how a reviewer judges "
                "whether the candidate understood why it stopped being able to fail."
            ),
        },
        {
            "path": "src/etlduck/db.py",
            "line_range": "63-70",
            "why": (
                "The quarantine table, declared with the comment stating that rows are kept "
                "rather than dropped because a pipeline that discards what it cannot parse "
                "reports clean numbers over an unknown amount of missing data."
            ),
        },
    ],
    "hints": [
        "Compare what `etlduck run --json` says about rejections against what is actually in "
        "the `quarantine` table. The committed deliveries contain ten rows that cannot be "
        "parsed, five per day.",
        "Find where silver decides a row cannot become a silver row. The rejection itself "
        "still works -- those rows are correctly kept out of `silver_usage` -- so look at "
        "what happens in the handler after the decision is made.",
        "The `except RowRejected` branch in `build_silver` just continues. It should insert "
        "the row into `quarantine` with its reason and increment the two counters, which is "
        "what the branch above it used to do.",
    ],
    "grading_notes": """\
**Root cause.** The `except RowRejected` branch in `src/etlduck/silver.py::build_silver`
continues without writing to `quarantine` or incrementing `rows_quarantined` and `reasons`.
The rejection decision itself is untouched and still correct — the ten bad rows are properly
kept out of `silver_usage`. What is gone is every record that they existed. The comment added
alongside gives the rationale: a table nobody reads.

**The expected fix** restores the insert and the two counters. Eight lines.

**Measured.** Nine tests fail, 127 pass. The run report:

| | silver_rows | quarantined | total_amount_cents | checks_passed |
|---|---|---|---|---|
| fixed | 400 | **10** | 817691 | true |
| broken | 400 | **0** | 817691 | true |

Silver and the money are **identical**. `etlduck check` passes, CI's quality step passes, and
the pipeline reports a flawless 0.00% rejection rate. Nothing anywhere says it is wrong.

**The point of the exercise, and S1 is the check for it.**
`check_quarantine_within_budget` computes its rate as `quarantine / (silver + quarantine)`.
With nothing ever recorded as quarantined, that is always 0, so the gate is **structurally
incapable of failing** — it will report all-clear through any upstream format change, which
is the one thing it exists to detect. The pipeline's self-reported health has become
unfalsifiable, and that is a strictly worse state than having no gate at all, because
somebody is relying on it.

The ten rows are not the damage. The brief says so and a candidate who spends their writeup
on the rows has missed the incident.

**Common wrong turns.**

- *Counted the rejections but did not store them* — incrementing `rows_quarantined` and
  skipping the insert. R1 passes, the gate can fire again, and R3 fails because the reasons
  are still lost. Partial credit; the gate works and the diagnosis does not. Explain that a
  rate tells you something changed and the reason tells you what, and only the second one
  shortens an incident.
- *Logged a warning instead of inserting.* Same shape: the gate still cannot fire, because it
  reads the table and not the log. R1 catches it. Worth noting in feedback that observability
  which is not queryable is not observability for a gate.
- *Let bad rows into `silver_usage`* with nulls or zeros so nothing is "lost". This is the
  worst available answer: it converts a known-unknown into silent corruption, breaks the
  reconciliation, and contradicts the whole "nothing is guessed" design. Several tests catch
  it. Cap correctness around 40 and set `symptom_patch_suspected`.
- *Raised instead of quarantining*, so one malformed row fails the whole build. The budget is
  deliberately not zero, and `ARCHITECTURE.md` says why: a handful of bad rows is normal and
  blocking on them means no warehouse at all on a bad day. R4 catches it.
- *Edited the tests, CI, `raw/` or the generator.* All protected. Hard F.

**On documentation.** The brief asks one thing: why the gate could no longer fire. A strong
`NOTES.md` traces it — the gate divides by a count that is now always zero — says that the
rows themselves were correctly rejected, and notes that the payload column exists so someone
can reconstruct what the producer actually sent. "Restored the quarantine insert" is correct
and worth a C+.
""",
}


# ---------------------------------------------------------------------------
# ex-027 -- fix a critical bug fast
# ---------------------------------------------------------------------------

EX027 = {
    "slug": "ex-027-dollars-stored-as-cents",
    "exercise_number": 27,
    "title": "Usage worth $12.50 was priced at 12 cents and the alert stopped firing",
    "exercise_type": ExerciseType.CRITICAL_BUG,
    "base_app": BaseApp.ETLDUCK,
    "difficulty": Difficulty.BEGINNER,
    "defect_class": "money_rounded_instead_of_rejected",
    "time_limit_minutes": 25,
    "expected_time_minutes": 15,
    "databases": [Database.DUCKDB],
    "needs_docker": True,
    "tags": ["etl", "duckdb", "money", "rounding", "validation"],
    "brief_md": """\
## DATA-1302 — usage priced at a hundredth of its value

**Severity:** SEV-1
**Reported by:** Revenue Assurance

One of our producers sends `amount_cents` with a decimal point in it — `"12.50"` — because
their field is in **dollars**. That has always been rejected, loudly, with the reason
`amount_not_integer_cents`, and somebody from our side would email them.

Since last week it is accepted instead, and stored as **12**. Twelve cents, for twelve
dollars fifty of usage.

### Reproducing it

```bash
docker compose up -d --wait
make test
etlduck run --json
```

The committed deliveries contain two of these rows, one per day.

### What we know

- `etlduck check` passes. Every quality gate is green.
- The run reports more rows in silver than it used to and **fewer** quarantined, and the
  rejection reason that used to appear in the breakdown is no longer in it at all.
- `raw/`, the tests, CI and the seed generator are off limits.

### Watch out for

There are two separate things wrong here and the money is only the first.

The value is wrong by about a factor of a hundred — but also, **the alert is gone.** The
reason this producer's mistake used to get fixed is that the pipeline refused the row and
somebody noticed. A pipeline that quietly accepts a plausible-looking number has removed
the only mechanism that was ever going to correct the source.

`ARCHITECTURE.md` states what a decimal in that column means and what to do about it. Say
in `NOTES.md` what the correct stored value would have been, and why coercing it is worse
than refusing it.
""",
    "definition_of_done": [
        "R1: tests/test_silver_parsing.py::test_a_decimal_amount_is_rejected_not_rounded passes",
        "R2: etlduck run --json reports the true total of 817691 cents",
        "R3: tests/test_silver_parsing.py::"
        "test_every_quarantine_reason_is_exercised_by_the_committed_data passes",
        "R4: the whole suite is green, with no test skipped, deleted or weakened",
        "R5: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md says what the value should have been and why refusing beats coercing",
    ],
    "focus_paths": ["src/etlduck/silver.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_silver_parsing.py::test_a_decimal_amount_is_rejected_not_rounded",
            "weight": 5,
            "required": True,
            "description": "A decimal in a cents column is refused, not rounded",
        },
        {
            "id": "R2",
            "kind": CheckKind.METRIC,
            "target": "etlduck run --json",
            "expect": {"metric": "total_amount_cents", "op": "==", "threshold": 817691},
            "weight": 4,
            "required": True,
            "description": (
                "The money is exactly right again. Pre-fix it is 817715 -- inflated by the "
                "24 cents the two coerced rows contributed"
            ),
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_silver_parsing.py::"
                "test_every_quarantine_reason_is_exercised_by_the_committed_data"
            ),
            "weight": 3,
            "required": True,
            "description": (
                "amount_not_integer_cents is back in the breakdown. The alert, not just the "
                "arithmetic"
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
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, CI, the committed deliveries and the seed generator are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Quantified it: '12.50' means 1250 cents and was stored as 12, understating "
                "that row by a factor of about a hundred -- rather than describing the fix "
                "as a rounding problem"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Noticed that the quarantine reason disappeared from the report, so the "
                "mechanism that used to get the producer's bug fixed is gone -- the second, "
                "less obvious half of the damage"
            ),
        },
    ],
    "baseline": baseline("ex-027-dollars-stored-as-cents"),
    "context_excerpts": [
        {
            "path": "ARCHITECTURE.md",
            "line_range": "67-88",
            "why": (
                "The 'Nothing is guessed' rules, which state that a decimal in amount_cents "
                "means the producer sent dollars and is 'worth an alert, not a silent "
                "halving'. The authority for refusing rather than coercing."
            ),
        },
        {
            "path": "src/etlduck/silver.py",
            "line_range": "1-19",
            "why": (
                "The module docstring, which states the money rule: integers throughout, "
                "because floats do not sum exactly. Needed to judge whether a candidate who "
                "reached for a float type understood what they were giving up."
            ),
        },
    ],
    "hints": [
        "Run `etlduck run --json` and compare the quarantine count and the reason breakdown "
        "against what the test suite says they should be. One reason is missing from the "
        "breakdown entirely, and that names the rule that stopped being enforced.",
        "`parse_cents` in `src/etlduck/silver.py` is what rejects a bad amount. Read what it "
        "now does to the text before turning it into an integer.",
        '`parse_cents` calls `int(round(float(text)))`, so `"12.50"` becomes 12 instead of '
        "raising `amount_not_integer_cents`. It should be `int(text)`, which refuses anything "
        "that is not already an integer.",
    ],
    "grading_notes": """\
**Root cause.** `src/etlduck/silver.py::parse_cents` parses with `int(round(float(text)))`
instead of `int(text)`. A decimal therefore no longer raises; it is coerced. The comment
added alongside gives the rationale -- tolerate a fractional cent rather than lose the row --
which is a plausible-sounding thing to want and the opposite of what this column needs.

**The expected fix** restores `int(text)`. One line.

**Measured.**

| | silver_rows | quarantined | total_amount_cents | checks_passed |
|---|---|---|---|---|
| fixed | 400 | 10 | **817691** | true |
| broken | 402 | 8 | **817715** | true |

Five tests fail, 131 pass, and every quality gate stays green. The two affected rows land in
silver as **12 cents each**, and `amount_not_integer_cents` vanishes from the quarantine
breakdown entirely.

**The magnitude, which S1 is the check for.** The producer's `"12.50"` means twelve dollars
fifty -- **1250 cents**. It was stored as 12. That is an understatement of 1238 cents on that
row, a factor of about 104. A candidate who describes this as "a rounding bug" has the
mechanism and not the consequence; the brief gives the figure in its title for a reason.

Worth knowing as a reviewer: Python rounds half to even, so `round(12.5)` is **12**, not 13.
Even the coercion goes the direction nobody predicts, which is a good illustration of why
guessing at a value is worse than refusing it.

**The second half of the damage, which S2 checks.** The reason this producer's mistake used
to get corrected is that the pipeline refused the row, the reason appeared in the quarantine
breakdown, and somebody emailed them. Accepting a plausible-looking number removes the only
feedback path to the source. The row is now wrong *and* the upstream will keep sending it.
That is why `ARCHITECTURE.md` says a decimal here is "worth an alert", and it is the more
transferable observation of the two.

**Common wrong turns.**

- *Multiplied by 100* -- `int(round(float(text) * 100))` -- on the theory that the producer
  sends dollars. It makes this row right and every *correct* row wrong by a hundredfold, and
  R2 catches it immediately. Worth engaging with in feedback: the inference about the
  producer is probably true, and acting on it inside the parser is still wrong, because the
  column's contract is cents and one producer's bug is not a reason to reinterpret everyone's
  data.
- *Changed the column to a float or a DECIMAL* so a decimal can be stored. R1 fails, and the
  module docstring explains the cost: floats do not sum exactly, so the reconciliation stops
  being exact and every total becomes order-dependent. Mark correctness down and quote it.
- *Used `Decimal`* and stored it rounded. More defensible, same outcome: the row is accepted
  when it should be refused. R1 fails.
- *Rejected the row but silently*, without the quarantine reason. R1 and R2 pass and R3
  fails. Partial credit; the money is right and the alert is still gone.
- *Edited the tests, CI, `raw/` or the generator.* All protected. Hard F.

**On documentation.** A beginner-tier one-line fix, so the writeup carries the grade. A strong
`NOTES.md` states that the value should have been 1250, quantifies the understatement, says
why refusing beats coercing, and notes that the missing quarantine reason is how the producer
used to find out. "parse_cents now rejects decimals" is accurate and worth a C+.
""",
}


# ---------------------------------------------------------------------------
# ex-028 -- build or fix an EDA/preprocessing library
# ---------------------------------------------------------------------------

#: Proves the property behaviourally: profile a delivery that sends numbers as JSON numbers
#: with legitimate zeroes, and require the null-like fraction to be 0%. Pre-fix it reports
#: 33.3% of the quantity column and 50% of the boolean column as missing.
FALSY_VALUES_PROBE = r"""d=$(mktemp -d)
python - "$d" <<'PY'
import json
import sys
from pathlib import Path

from etlduck.profile import profile_jsonl

scratch = Path(sys.argv[1])
path = scratch / "usage_events_2026-03-01.jsonl"
records = [
    {
        "event_id": f"evt-{n}",
        "account_id": "acct-000",
        "event_type": "api_call",
        "occurred_at": "2026-03-01T10:00:00+00:00",
        "quantity": 0 if n % 3 == 0 else n,
        "billable": False if n % 2 == 0 else True,
        "amount_cents": 100,
    }
    for n in range(30)
]
path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

profile = profile_jsonl(path)
quantity = profile.fields["quantity"]
billable = profile.fields["billable"]
assert quantity.null_fraction() == 0.0, (
    f"a quantity of 0 was reported as missing: {quantity.null_fraction():.1%} of the column"
)
assert billable.null_fraction() == 0.0, (
    f"a billable of False was reported as missing: {billable.null_fraction():.1%} of the column"
)
print("ok: zero and False are values, not absences")
PY
"""

EX028 = {
    "slug": "ex-028-zero-reported-as-missing",
    "exercise_number": 28,
    "title": "The pre-ingest profile claims a third of a column is missing when none of it is",
    "exercise_type": ExerciseType.EDA_LIBRARY,
    "base_app": BaseApp.ETLDUCK,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "falsy_values_treated_as_missing",
    "time_limit_minutes": 30,
    "expected_time_minutes": 18,
    "databases": [Database.DUCKDB],
    "needs_docker": True,
    "tags": ["etl", "profiling", "data-quality", "python", "truthiness"],
    "brief_md": """\
## DATA-1319 — two hours chasing a schema change that never happened

**Severity:** SEV-3
**Reported by:** whoever was on call on Saturday

A new producer went live. It sends `quantity` and `billable` as **JSON numbers and
booleans** rather than as strings, which is allowed — bronze keeps every value as text and
type inference is a later, separate step.

`etlduck profile` reported a third of their `quantity` column and half of their `billable`
column as missing. On-call escalated to the producer, who correctly pointed out that every
record has both fields populated. Two hours, no bug at their end.

The values being reported as missing are **zeroes and falses**. A day with no API calls is
zero. A line item that is not billable is false. Both are answers.

### Reproducing it

```bash
docker compose up -d --wait
make test
```

Two tests fail and both are parametrized cases of the same test, which is named after the
property. To see the reported figures, profile a file whose numeric fields are JSON numbers
with some zeroes in them — about eight lines.

### What we know

- A producer that sends `"0"` as a **string** is unaffected, which is why this looked
  specific to the new one and why nobody saw it in our own sample files.
- Nothing is lost. Profiling never rejects anything; it only describes. The numbers it
  describes with are wrong.
- `raw/`, the tests, CI and the seed generator are off limits.

### Watch out for

A profile is an early-warning system: somebody compares today's report against yesterday's
and escalates on a difference. A report that invents missing data costs exactly what a
report that hides it costs — once it has cried wolf, the next real schema change gets
ignored.

In `NOTES.md`, say why a string `"0"` behaved differently from a numeric `0`, and what
distinction the check should actually be making.
""",
    "definition_of_done": [
        "R1: a column of JSON numbers containing zeroes profiles as 0% missing",
        "R2: tests/test_quality_cli_profile.py::test_values_that_are_not_null_tokens passes",
        "R3: the whole suite is green, with no test skipped, deleted or weakened",
        "R4: bash ci/run_ci.sh exits 0",
        'llm: NOTES.md says why a string "0" behaved differently from a numeric 0',
    ],
    "focus_paths": ["src/etlduck/profile.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.CMD,
            "target": FALSY_VALUES_PROBE,
            "expect": {"exit_code": 0},
            "weight": 5,
            "required": True,
            "description": (
                "The property, proved behaviourally: zeroes and falses are values. Pre-fix "
                "the probe reports 33.3% of the quantity column as missing"
            ),
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_quality_cli_profile.py::test_values_that_are_not_null_tokens",
            "weight": 4,
            "required": True,
            "description": (
                "All six cases. Two fail pre-fix -- the integer 0 and False -- and the four "
                "string cases pass either way, which is the shape of the bug"
            ),
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": (
                "No regressions -- specifically that the recognised null spellings still "
                "count as missing, which a fix that only checks for None would break"
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
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, CI, the committed deliveries and the seed generator are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Explained the mechanism precisely: `not value` is true for 0, False and the "
                "empty string alike, so Python's truthiness was being used to answer a "
                "question about presence -- and only `None` means absent here"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                'Observed why it looked producer-specific: a string "0" is truthy, so only '
                "producers sending real JSON numbers or booleans were affected, and the "
                "committed sample files send everything as strings"
            ),
        },
    ],
    "baseline": baseline("ex-028-zero-reported-as-missing"),
    "context_excerpts": [
        {
            "path": "src/etlduck/profile.py",
            "line_range": "1-27",
            "why": (
                "The module docstring and the NULL_TOKENS set, which state that profiling "
                "describes rather than rejects and which spellings count as missing. The "
                "contract the fix has to keep while narrowing what counts as absent."
            ),
        },
        {
            "path": "src/etlduck/silver.py",
            "line_range": "29-64",
            "why": (
                "The KNOWN_EVENT_TYPES block and the rejection machinery, for contrast: "
                "silver is the layer that refuses things, with a reason. A candidate who "
                "proposes rejecting in the profiler has the layers confused."
            ),
        },
    ],
    "hints": [
        "Profile a file whose `quantity` field is a JSON number rather than a quoted string, "
        "with some zeroes among the values, and look at the reported null-like fraction. Then "
        'do the same with `"0"` quoted and compare.',
        "`is_null_token` in `src/etlduck/profile.py` decides what counts as missing. Read its "
        "first branch and ask which Python values satisfy it.",
        'The first branch is `if not value`, which is true for `None`, `0`, `False` and `""` '
        "alike. Only `None` means absent; the empty string is already handled by the "
        "`NULL_TOKENS` check below.",
    ],
    "grading_notes": """\
**Root cause.** `src/etlduck/profile.py::is_null_token` opens with `if not value: return
True`. That is Python's truthiness, not a test for presence: it is satisfied by `None`, by
the integer `0`, by `False` and by the empty string. The comment added alongside argues they
all mean the same thing to a reader of the report, which is exactly the confusion -- a day
with no API calls is zero, and that is an answer.

**The expected fix** restores `if value is None`. One line. The empty string is already
covered by the `NULL_TOKENS` check below it, which is why narrowing the first branch loses
nothing.

**Measured.** Exactly 2 of 136 tests fail -- both parametrized cases of
`test_values_that_are_not_null_tokens`, the integer `0` and `False`. The four string cases
pass either way. The probe shows the reported damage:

| column | values | fixed | broken |
|---|---|---|---|
| `quantity` | 10 of 30 are `0` | 0.0% missing | **33.3% missing** |
| `billable` | 15 of 30 are `False` | 0.0% missing | **50.0% missing** |

**Why nobody saw it internally (S2).** A string `"0"` is truthy, so the bug only affects
producers sending genuine JSON numbers and booleans. Every file under `raw/` is generated
with string values, so the whole committed corpus is immune -- which is why this reached
production and why the brief frames it as producer-specific. That is the same class of
finding as the catalog's other fixture-blindness cases: a library whose tests run against
its own tidy sample data keeps learning about its edge cases from users.

**What the exercise is for.** A profile is an early-warning system, and this is the *false
alarm* failure mode -- the exact inverse of a pipeline that reports a 0% rejection rate while
discarding rows. Both destroy the same thing. A report that invents missing data gets
ignored, and the next real schema change goes with it. Two hours of on-call time is the
cheap version of that cost. S1 checks whether the candidate named the mechanism rather than
the symptom: truthiness was used to answer a question about presence.

**Common wrong turns.**

- *Checked `if value is None or value == ""`.* Correct, slightly redundant -- the empty
  string already falls through to `NULL_TOKENS` -- and fully acceptable. Do not mark it down;
  if anything it is more explicit. Note the redundancy in feedback.
- *Special-cased the types* -- `if isinstance(value, (int, float, bool)): return False`. Works
  and passes everything, but it inverts the logic: the function should say what *is* absent,
  not enumerate what is not. Correctness full, engineering around 70.
- *Removed `""` from `NULL_TOKENS`* while keeping `if not value`. The empty string is still
  caught by the truthiness branch, so this changes nothing and the two tests still fail. A
  candidate who tries it and re-runs has done fine; one who claims it as the fix has not
  verified.
- *Made the profiler reject or raise on an ambiguous value.* Wrong layer. Profiling describes
  and never rejects -- that is the first line of its module docstring -- and rejection with a
  reason is silver's job. Correctness around 55 and point at both.
- *Changed the producer's data, or proposed requiring string values.* The brief says JSON
  numbers are allowed and bronze keeps everything as text regardless. The library is wrong,
  not the producer.
- *Edited the tests, CI, `raw/` or the generator.* All protected. Hard F.

**On documentation.** The brief asks one precise question: why a string `"0"` behaved
differently from a numeric `0`. A strong `NOTES.md` answers with truthiness, notes that only
`None` means absent in this function, and observes that the sample data could never have
caught it. "is_null_token now checks for None" is correct and worth a C+.
""",
}


# ---------------------------------------------------------------------------
# ex-029 -- fix a broken CI/CD pipeline
# ---------------------------------------------------------------------------

#: ex-029 repairs ``ci/run_ci.sh``, so unlike every other exercise here that file cannot be
#: protected. The workflow takes its place as the immovable reference: it is the half that is
#: still correct, so the drift has exactly one right direction to be closed in.
CI_FROZEN = [
    "tests/**",
    "pyproject.toml",
    ".github/workflows/ci.yml",
    "ci/pipeline_smoke.sh",
    "raw/**",
    "tools/gen_seed_data.py",
]

#: The gate the workflow still runs and the local mirror no longer does. Asserts the cluster
#: policy pins the session timezone rather than merely allowing UTC among other options.
POLICY_PINS_UTC = (
    'python -c "\n'
    "import json, pathlib\n"
    "policy = json.loads(pathlib.Path('dbx_conf/cluster_policy.json').read_text())\n"
    "zone = policy['spark_conf.spark.sql.session.timeZone']\n"
    "assert zone['type'] == 'fixed' and zone['value'] == 'UTC', zone\n"
    "print('session timeZone is fixed to UTC')\n"
    '"'
)

EX029 = {
    "slug": "ex-029-green-locally-red-on-github",
    "exercise_number": 29,
    "title": "GitHub is failing on a step that make ci does not run",
    "exercise_type": ExerciseType.CICD_PIPELINE,
    "base_app": BaseApp.ETLDUCK,
    "difficulty": Difficulty.BEGINNER,
    "defect_class": "ci_mirror_dropped_a_config_gate",
    "time_limit_minutes": 25,
    "expected_time_minutes": 15,
    "databases": [Database.DUCKDB],
    "needs_docker": True,
    "tags": ["ci", "github-actions", "databricks", "config", "timezones"],
    "brief_md": """\
## DATA-1333 — CI is red and nobody can reproduce it

**Severity:** SEV-3
**Reported by:** everyone trying to merge

GitHub has been failing for two days on a step called **"Cluster policy parses and pins
UTC"**. Locally, `make test` is green and `make ci` is green. Three people have now run
both and concluded the build machine is broken.

The build machine is not broken.

### Reproducing it

```bash
docker compose up -d --wait
make test     # green
make ci       # green
```

Then read `.github/workflows/ci.yml` and `ci/run_ci.sh` **side by side** and find the step
GitHub is running that `make ci` is not.

### What we know

- The failing step is about `dbx_conf/cluster_policy.json`, not about the pipeline. Nothing
  is wrong with the data.
- Both halves of the CI definition currently list the same **number** of steps, which is why
  a couple of people have already decided they are in step. Counting them is not comparing
  them.
- `raw/`, the tests, the seed generator and `.github/workflows/ci.yml` are off limits. The
  workflow is the half we believe is correct.

### Watch out for

There are **two** things to put right and they are in different files. One is the
configuration the step is complaining about. The other is the reason nobody saw it coming —
and leaving that one unfixed guarantees a repeat.

`ARCHITECTURE.md` explains what the cluster policy is for and why that particular setting is
pinned rather than defaulted. In `NOTES.md`, connect it to something the pipeline actually
does: the setting is not arbitrary, and `dbx_conf/cluster_policy.json` says how many rows it
would affect.
""",
    "definition_of_done": [
        "R1: the cluster policy pins the session timezone to UTC",
        "R2: ci/run_ci.sh runs the cluster-policy step again",
        "R3: bash ci/run_ci.sh exits 0",
        "R4: the test suite stays green, with no test skipped, deleted or weakened",
        "llm: NOTES.md connects the pinned timezone to what the pipeline does with dates",
    ],
    "focus_paths": ["dbx_conf/cluster_policy.json", "ci/run_ci.sh"],
    "protected_paths": [*CI_FROZEN],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.CMD,
            "target": POLICY_PINS_UTC,
            "expect": {"exit_code": 0},
            "weight": 4,
            "required": True,
            "description": (
                "The gate GitHub is failing, run directly: the policy must pin the timezone, "
                "not merely allow UTC among other values"
            ),
        },
        {
            "id": "R2",
            "kind": CheckKind.GREP_PRESENT,
            "target": r"Cluster policy",
            "paths": ["ci/run_ci.sh"],
            "weight": 4,
            "required": True,
            "description": (
                "The local mirror runs the step again. Without this the policy is fixed and "
                "the next drift is just as invisible"
            ),
        },
        {
            "id": "R3",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 3,
            "required": True,
            "description": (
                "The restored step passes rather than merely existing -- so it cannot be "
                "added back in a form that never checks anything"
            ),
        },
        {
            "id": "R4",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 2,
            "required": True,
            "description": (
                "The suite stays green. It was green before the fix too, which is the point "
                "of the exercise rather than an oversight"
            ),
        },
        {
            "id": "R5",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*CI_FROZEN],
            "weight": 0,
            "required": True,
            "description": (
                "Tests, deliveries, the generator and the workflow are untouched. The "
                "workflow is the reference the local script has to be brought back to"
            ),
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Connected the setting to the pipeline: every date in the warehouse is "
                "derived from a UTC instant, so a cluster running in a local zone would "
                "bucket events into the wrong day -- the policy comment quantifies it at 58 "
                "of 400 rows in the sample data"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Noticed that the two halves now list the same number of steps, so a count "
                "says they agree while a comparison says they do not -- and proposed "
                "something that would catch the next divergence"
            ),
        },
    ],
    "baseline": baseline("ex-029-green-locally-red-on-github"),
    "context_excerpts": [
        {
            "path": ".github/workflows/ci.yml",
            "line_range": "1-60",
            "why": (
                "The correct half of the mirror, and therefore the answer key for the drift. "
                "Needed to judge whether the candidate restored the step the workflow "
                "actually runs or invented their own."
            ),
        },
        {
            "path": "ARCHITECTURE.md",
            "line_range": "134-145",
            "why": (
                "The 'Databricks shape' section, which states that CI parses all three asset "
                "kinds and that they are documentation which is checked. The argument for "
                "restoring the step rather than only the setting."
            ),
        },
    ],
    "hints": [
        "Run `make ci` and list its step headers. Then list the `- name:` steps in "
        "`.github/workflows/ci.yml`. One name appears in the workflow and not in the script, "
        "and it is the one GitHub is failing on.",
        "Run the missing step by hand: it loads `dbx_conf/cluster_policy.json` and asserts "
        "something about `spark_conf.spark.sql.session.timeZone`. Read what the assertion "
        "requires, then read what the file currently says.",
        'The policy\'s timezone entry was changed from `"type": "fixed"` with UTC to an '
        "allowlist defaulting to `Europe/Berlin`. Both need fixing: the setting back to "
        "fixed UTC, and the step back into `ci/run_ci.sh` so the next change cannot pass "
        "unnoticed.",
    ],
    "grading_notes": """\
**Root cause, in two files and in this order.** Somebody removed the "Cluster policy parses
and pins UTC" step from `ci/run_ci.sh`. With nothing checking it locally, the policy's
`spark_conf.spark.sql.session.timeZone` was later changed from
`{"type": "fixed", "value": "UTC"}` to an allowlist defaulting to `Europe/Berlin` — and
nobody found out until GitHub, which still runs the step, went red.

**The expected fix is both halves.** Re-pin the policy *and* restore the step. Fixing only
the policy makes GitHub green and leaves the next drift exactly as invisible, which is what
R2 is for.

**Measured.** The suite is **136 passed before and after**; `make test` is green in both
states. `bash ci/run_ci.sh` exits **0** in the broken state — that is the whole complaint —
while the step the workflow runs fails with the policy dict printed, including its own
comment explaining why the setting is pinned.

**The trap worth knowing about as a reviewer.** Pristine `ci/run_ci.sh` has **9** steps and
the workflow has **8**, because the script also prints the Python version while the workflow
pins it in `setup-python`. After the removal the script has 8 and the workflow has 8 — the
counts *coincidentally agree*. Anyone who compares counts rather than contents concludes the
mirror is in step, which the brief says two people have already done. S2 is whether the
candidate noticed.

**What makes a strong answer (S1).** The setting is not arbitrary configuration. Every date in
this warehouse is derived from a UTC instant, and the policy's own comment says a cluster
configured to a local zone would bucket a slice of events into the wrong day — "measured at
58 of 400 rows in the sample data". A candidate who connects the two has understood that the
policy is a guard against the same failure the pipeline's date handling guards against, one
layer down. One who treats it as a lint rule about a JSON file has fixed the build and
learned nothing.

**Common wrong turns.**

- *Fixed the policy, left the step out.* The most likely submission: GitHub goes green and
  the job is apparently done. R2 catches it. Worth saying in feedback that the missing step
  is the actual defect — the policy change was only able to happen because of it.
- *Restored the step, left the policy.* R1 and R3 both catch it: the step now exists and
  fails.
- *Added the step back in a weakened form* — checking the key exists, or accepting the
  allowlist. R3 passes and R1 fails, because R1 runs the workflow's assertion rather than
  the candidate's. That separation is deliberate.
- *Edited `.github/workflows/ci.yml`* to drop or soften the step. Protected, so the tampering
  gate fires. This is closing the drift in the wrong direction and it is how an incident
  becomes permanent — worth explaining rather than only penalising.
- *Added `Europe/Berlin` handling to the pipeline* so a local-zone cluster would be safe.
  Ambitious, wrong layer, and it contradicts the design: the warehouse normalises everything
  to UTC precisely so no component has to care. Mark engineering down and point at
  `ARCHITECTURE.md`.
- *Edited the tests, `raw/` or the generator.* Protected. Hard F, and irrelevant — nothing
  about the data is wrong here.

**On documentation.** A beginner-tier exercise with a two-file fix, so the writeup carries the
grade. A strong `NOTES.md` names both changes, explains that the local script could never have
caught the second one, connects the pinned timezone to the pipeline's date handling with the
58-of-400 figure, and ideally proposes something that would catch the next divergence —
having the workflow call `ci/run_ci.sh` as its single step is the cleanest answer. "Re-pinned
UTC and restored the CI step" is correct and worth a C+.
""",
}


#: Every authored ``etlduck`` exercise, in catalog order. Complete at its planned 8.
EXERCISES: list[dict] = [EX022, EX023, EX024, EX025, EX026, EX027, EX028, EX029]
