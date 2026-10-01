"""Exercises built on the ``edakit`` base application.

Same ``(base_app, mutations)`` shape as the other catalog modules, and baselines are
likewise **measured** into ``baselines.json`` by the verification harness rather than
authored here.

What makes this base app different is that it is a **library**, not a service. There is
no request to trace and no deploy to blame: a defect here is wrong arithmetic or a broken
contract that every consumer inherits silently. Several of its exercises therefore turn
on a property the library documents about itself rather than on an observable outage.
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


#: The tests are the proof, so editing them is tampering. ``pyproject.toml`` is in here
#: rather than a ``pytest.ini`` because that is where this package keeps its pytest
#: configuration, including the ``--doctest-modules`` flags. ``datasets/`` is protected
#: because the suite runs against those real files: editing a messy CSV to be less messy
#: makes a test pass without fixing anything.
STANDARD_PROTECTED = [
    "tests/**",
    "pyproject.toml",
    "ci/run_ci.sh",
    "datasets/**",
]

#: Shared context: the fit/transform contract, which is the single property most of this
#: library's design follows from.
FIT_TRANSFORM_EXCERPT = {
    "path": "ARCHITECTURE.md",
    "line_range": "19-32",
    "why": (
        "States the fit/transform contract and why it is not stylistic: a transformer "
        "that recomputes at transform time maps the same row to different numbers "
        "depending on its batch. The rule any fix at this seam is judged against."
    ),
}


# ---------------------------------------------------------------------------
# ex-017 -- build or fix an EDA/preprocessing library
# ---------------------------------------------------------------------------

EX017 = {
    "slug": "ex-017-scaler-depends-on-the-batch",
    "exercise_number": 17,
    "title": "The same customer gets a different feature value depending on who else is in the batch",
    "exercise_type": ExerciseType.EDA_LIBRARY,
    "base_app": BaseApp.EDAKIT,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "transform_recomputes_statistics",
    "time_limit_minutes": 30,
    "expected_time_minutes": 18,
    "databases": [],
    "needs_docker": True,
    "tags": ["python", "library", "preprocessing", "scaling", "train-serve-skew"],
    "brief_md": """\
## EDAKIT-312 — scaled features depend on the batch they arrive in

**Reported by:** the recommendations team, who depend on this package

They scale features with `edakit` before scoring. Last week they moved from nightly
batch scoring to scoring each account as it arrives, and their model's output shifted
for accounts whose inputs had not changed at all.

Their reproduction, which they sent us:

```python
from edakit import fit_scaler, ScalerKind

scaler = fit_scaler([10.0, 20.0, 30.0, 40.0], ScalerKind.STANDARD)
print(scaler.transform([10.0, 20.0, 30.0, 40.0]))   # the whole batch
print(scaler.transform([10.0]))                     # the first row on its own
```

The value 10.0 is the same number, scaled by the same fitted scaler, and comes out
differently depending on what was passed alongside it.

### Reproducing it

```bash
docker compose up -d --wait
make test
```

### What we know

- This is our bug, not theirs. They are holding the scaler and reusing it, which is
  exactly what the README tells them to do.
- `datasets/` and the test suite are off limits.
- One of the failing tests is named after the property being broken.

### Watch out for

The code you are about to read has a **rationale** attached to it, and the rationale is
not stupid: distributions really do drift away from whatever a transformer was fitted on.
You need to decide whether adapting at transform time is the right response to that, and
if it is not, say in `NOTES.md` what the right response is. Do not just delete something
without engaging with why somebody added it.

Worth asking yourself before you finish: this package has four other transformers. Do
any of them have the same problem?
""",
    "definition_of_done": [
        "R1: tests/test_outliers_scale_encode.py::test_transform_is_independent_of_the_batch passes",
        "R2: tests/test_outliers_scale_encode.py::test_standard_scaler_centres_and_scales passes",
        "R3: the whole suite is green, with no test skipped, deleted or weakened",
        "R4: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md engages with the drift rationale the broken code was written for, "
        "and says what the right response to drift actually is",
    ],
    "focus_paths": ["src/edakit/scale.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_outliers_scale_encode.py::test_transform_is_independent_of_the_batch"
            ),
            "weight": 4,
            "required": True,
            "description": (
                "The library's headline invariant: one row scales the same alone as it "
                "does inside a mixed batch"
            ),
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_outliers_scale_encode.py::test_standard_scaler_centres_and_scales"
            ),
            "weight": 3,
            "required": True,
            "description": "Hand-computed scaling: fitted on mean 5 / sd 2, 9 maps to 2.0",
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
            "description": "The CI pipeline passes, docstring examples included",
        },
        {
            "id": "R5",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, pytest configuration, the CI script and the datasets are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Argued against the drift rationale rather than ignoring it: the answer "
                "to drift is refitting on new data and shipping a new transformer, not "
                "adapting inside transform, because the latter destroys comparability "
                "between any two batches"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Checked the other transformers -- Imputer, OneHotEncoder, "
                "OrdinalEncoder -- for the same mistake and reported the result, rather "
                "than fixing only the one the failing test named"
            ),
        },
    ],
    "baseline": baseline("ex-017-scaler-depends-on-the-batch"),
    "context_excerpts": [
        FIT_TRANSFORM_EXCERPT,
        {
            "path": "src/edakit/missing.py",
            "line_range": "89-130",
            "why": (
                "Imputer.transform, which is the contract implemented correctly: the "
                "learned values live on the object and transform is a pure lookup. The "
                "shape a fixed Scaler.transform should match, and the comparison a "
                "thorough candidate makes unprompted."
            ),
        },
    ],
    "hints": [
        "Run the snippet from the brief yourself, then read `Scaler.transform` in "
        "`src/edakit/scale.py` and ask which of the numbers it uses came from "
        "`fit_scaler` and which came from the argument.",
        "Compare `Scaler.transform` against `Imputer.transform` in "
        "`src/edakit/missing.py`. One of them consults only what it learned at fit time; "
        "the other does not.",
        "`transform` recomputes `centre` and `spread` from `values` for every call, "
        "falling back to the fitted `spread` only when the batch is degenerate. It should "
        "use `self.centre` and `self.spread` unconditionally -- the two lines the "
        "original implementation had.",
    ],
    "grading_notes": """\
**Root cause.** `src/edakit/scale.py::Scaler.transform` re-derives `centre` and `spread`
from the series it is given, per call, mirroring the logic in `fit_scaler` and keeping the
fitted values only as a fallback for a batch with no spread. The fitted parameters are
therefore ignored whenever the batch has any variation at all.

**The expected fix** is to restore the two-line form:
`[(value - self.centre) / self.spread for value in values]`.

**Measured.** 2 of 131 tests fail -- `test_transform_is_independent_of_the_batch` and
`test_standard_scaler_centres_and_scales` -- and `ci/run_ci.sh` fails because the suite
does. The benchmark is unaffected (2.5 reads per cell either way): this is a correctness
defect, not a performance one. The symptom from the brief, scaling `[10, 20, 30, 40]`
after fitting on the same series, gives `[-1.3416, -0.4472, 0.4472, 1.3416]` for the
batch and `[0.0]` for the first row alone.

**What the exercise is really testing.** The defect ships with a coherent justification
written into its own docstring -- distributions drift, so re-centring on the batch keeps
values in a sensible range. That is a real problem with a wrong solution, and the grade
should turn on whether the candidate engages with it. The argument to look for (S1,
weighted 2): adapting inside `transform` means two batches are no longer comparable with
each other *or* with anything the model was trained on, so it does not mitigate drift, it
hides drift while corrupting every number. The right response is to refit on new data and
ship a new transformer, with the old one kept for reproducibility.

A submission that reverts two lines and says "transform should use the fitted values" is
correct and shallow. One that says why the alternative is seductive and still wrong is the
difference between a B and an A here.

**S2** is the breadth check. The package has four other transformers, and
`Imputer.transform`, `OneHotEncoder.transform_one` and `OrdinalEncoder.transform_one` are
all correct pure lookups. Reporting that they were checked and are fine is worth credit;
it is the difference between fixing a test and auditing a contract.

**Common wrong turns.**

- *Kept the recomputation behind a flag* -- `transform(values, adapt=False)` or an
  `adaptive` attribute. Every objective check passes if the default is correct. It still
  leaves a documented way to produce incomparable features, and the README's promise
  becomes conditional. Correctness full, engineering around 60, and say plainly that an
  option nobody should choose is not an improvement on no option.
- *Removed the fallback but kept recomputing*, so a constant batch now divides by zero.
  Breaks `test_a_constant_column_scales_to_zeros_rather_than_dividing_by_zero`, which is
  the test that exists for exactly this.
- *Edited the failing tests*, `datasets/` or `pyproject.toml`. All protected. Hard F.
  Note that `pyproject.toml` is protected here because it holds the pytest configuration,
  so weakening collection is the same move as editing a test.
- *Fixed `Scaler` and silently "tidied" another transformer* that was already correct.
  Check the diff: unnecessary edits to `missing.py` or `encode.py` in an exercise about
  `scale.py` are scope creep, and in a library they are a compatibility risk for
  consumers. Mark engineering down modestly.
- *Concluded the reporting team should pass whole batches.* That is blaming the caller
  for using the documented API correctly, and it is worth saying so directly in feedback.

**On documentation.** The brief asks two things beyond the fix: engage with the drift
rationale, and say whether the other transformers share the problem. A `NOTES.md` that
does both is an A. One that describes the two-line revert has fixed the library and
demonstrated none of the judgement the defect was constructed to test, and should not
clear a B−.
""",
}


# ---------------------------------------------------------------------------
# ex-018 -- build or fix an EDA/preprocessing library
# ---------------------------------------------------------------------------

EX018 = {
    "slug": "ex-018-boolean-flags-typed-as-integers",
    "exercise_number": 18,
    "title": "A 0/1 flag column is being averaged, and 0.75 is now a valid value for is_active",
    "exercise_type": ExerciseType.EDA_LIBRARY,
    "base_app": BaseApp.EDAKIT,
    "difficulty": Difficulty.BEGINNER,
    "defect_class": "type_inference_order_boolean_vs_integer",
    "time_limit_minutes": 25,
    "expected_time_minutes": 15,
    "databases": [],
    "needs_docker": True,
    "tags": ["python", "library", "type-inference", "imputation", "data-quality"],
    "brief_md": """\
## EDAKIT-318 — our boolean flags are being treated as numbers

**Reported by:** the billing analytics team

Their warehouse export renders booleans as `0` and `1`, which is what most SQL exports
do. Until the last release `edakit` recognised those columns as boolean and **refused**
to mean-impute them. Now it accepts the request and fills the gaps with values like
`0.75`.

They noticed because a dashboard started showing accounts that were 75% active.

Their reproduction:

```python
from edakit.schema_infer import infer_column_type
from edakit import fit_imputer, Strategy

flags = ["1", "0", "1", "1", "0", "1", "1", "1"]
print(infer_column_type(flags))          # what type is this column?

rows = [{"is_active": v} for v in flags] + [{"is_active": ""}]
imputer = fit_imputer(rows, {"is_active": Strategy.MEAN},
                      column_types={"is_active": infer_column_type(flags)})
print(imputer.fill_values["is_active"])  # what gets written into the hole?
```

### Reproducing it

```bash
docker compose up -d --wait
make test
```

One test fails, and its docstring states the rule being broken.

### What we know

- The guard that rejects numeric strategies on non-numeric columns is working fine.
  It is being handed the wrong answer, not reaching the wrong conclusion.
- Nothing in `datasets/` is affected, because our own sample files spell booleans
  `true`/`false`. That is why this reached a release.
- `is_active` columns spelled `true`/`false` still behave correctly.

### Watch out for

Two types can both be a legitimate reading of the same text. The question is not "which
pattern matches" but "which reading is more specific" — `0` and `1` are valid integers
*and* valid booleans, and only one of those readings lets the rest of the library protect
the column. Say which rule you applied in `NOTES.md`.
""",
    "definition_of_done": [
        "R1: tests/test_schema_infer.py::test_booleans_win_over_integers passes",
        "R2: the whole suite is green, with no test skipped, deleted or weakened",
        "R3: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md states the ordering rule and why the more specific reading wins",
    ],
    "focus_paths": ["src/edakit/schema_infer.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_schema_infer.py::test_booleans_win_over_integers",
            "weight": 5,
            "required": True,
            "description": "A 0/1 column is inferred as boolean, the more specific reading",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": (
                "No regressions. Matters more than usual here: the inference order is a "
                "chain, and fixing one link can break another"
            ),
        },
        {
            "id": "R3",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 2,
            "required": True,
            "description": "The CI pipeline passes",
        },
        {
            "id": "R4",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, pytest configuration, the CI script and the datasets are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Explained the ordering as specificity rather than as an arbitrary "
                "sequence -- boolean before integer, integer before float -- and noticed "
                "that the integer-before-float rule is the same principle"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Noticed that none of the shipped datasets spell booleans 0/1, so the "
                "suite could only catch this through a unit test and never through the "
                "dataset-driven ones -- and said what that implies about the fixtures"
            ),
        },
    ],
    "baseline": baseline("ex-018-boolean-flags-typed-as-integers"),
    "context_excerpts": [
        {
            "path": "src/edakit/missing.py",
            "line_range": "176-190",
            "why": (
                "The guard in fit_imputer that rejects a numeric strategy on a "
                "non-numeric column. It is correct and is not the bug -- it was simply "
                "told the column was an integer. Needed so the candidate's fix is judged "
                "at the inference layer rather than here."
            ),
        },
        {
            "path": "src/edakit/schema_infer.py",
            "line_range": "43-51",
            "why": (
                "The cardinality constants and their comments, which show the module's "
                "house style: every classification decision is explicit and justified "
                "in a comment. A fix that reorders silently does not match it."
            ),
        },
    ],
    "hints": [
        "Run the snippet from the brief. The first line prints the inferred type -- that "
        "is the answer the rest of the library is acting on, so start there rather than "
        "at the imputer.",
        "Read `infer_column_type` in `src/edakit/schema_infer.py`. It tries each type in "
        'sequence and returns the first match. Ask what `"0"` and `"1"` match, and in '
        "what order those checks now appear.",
        "The integer check sits above the boolean check. It has to be below it, because "
        "every `0`/`1` value matches both patterns and boolean is the narrower reading. "
        "The docstring of the failing test states this.",
    ],
    "grading_notes": """\
**Root cause.** `src/edakit/schema_infer.py::infer_column_type` tries the integer pattern
before the boolean one. Since `0` and `1` match both, a flag column returns `INTEGER` and
never reaches the boolean branch. The function's own docstring was updated to match the new
order, so the code is internally consistent and reads fine -- the surviving statement of
the rule is the docstring of `test_booleans_win_over_integers`.

**The expected fix** moves the boolean check back above the integer check. Four lines.

**Measured.** Exactly 1 of 131 tests fails and `ci/run_ci.sh` fails because the suite does.
The consequence the brief describes is real: a 0/1 column infers as `integer`, and
`fit_imputer` with `MEAN` then **accepts** the request and learns a fill value of `0.75`.
On the fixed library the same call raises
`column 'is_active' is boolean but strategy mean is numeric-only`.

Note what that means about the defect: the guard in `fit_imputer` is working perfectly. It
rejects numeric strategies on non-numeric columns and would have rejected this one. It was
handed the wrong type. A candidate who "fixes" `fit_imputer` has misread which layer is
wrong, and the brief says so explicitly.

**Why it shipped, which is worth drawing out.** None of the files in `datasets/` spells a
boolean as 0/1 -- `customers.csv` uses `true`/`false`. So every dataset-driven test in the
suite passes, and only the hand-written unit test covers the case. That is S2: the fixtures
were not representative of the inputs consumers actually send, and a library whose tests run
against its own tidy sample files will keep finding this out from its users.

**What separates a strong answer.** The ordering is not arbitrary, it is specificity:
boolean before integer because every 0/1 is both and boolean is narrower; integer before
float for exactly the same reason, since every integer also matches the float pattern. A
candidate who states that principle has understood the function; one who says "moved two
lines" has not. That is S1.

**Common wrong turns.**

- *Relaxed the guard in `fit_imputer`* so mean-imputation works on booleans. The required
  check fails, and it is worth saying in feedback that this makes a correct safety check
  responsible for an inference bug.
- *Special-cased `{"0", "1"}`* ahead of the integer check instead of restoring the order.
  Works, passes everything, and leaves the general rule broken: a column of `"t"`/`"f"`
  is still fine but the sequencing principle is now expressed as an exception. Correctness
  full, engineering around 65, and explain that the ordering *was* the mechanism.
- *Moved the boolean check above the integer one but also above the EMPTY guard*, so an
  all-null column stops being `EMPTY`. `test_an_all_null_column_is_empty_not_guessed`
  catches it; R2 is why the suite check carries weight here.
- *Edited the failing test, `pyproject.toml` or `datasets/`.* All protected. Hard F. Adding
  a 0/1 flag column to `customers.csv` would be a *good* instinct expressed as tampering --
  say so, and credit the instinct if `NOTES.md` proposes it rather than doing it.

**On documentation.** This is a four-line fix, so the writeup carries the grade. A strong
`NOTES.md` names the specificity rule, identifies that the imputer guard was innocent, and
ideally observes that the sample datasets could never have caught it. "Reordered the type
checks" is accurate and worth a C+.
""",
}


# ---------------------------------------------------------------------------
# ex-019 -- build or fix an EDA/preprocessing library
# ---------------------------------------------------------------------------

EX019 = {
    "slug": "ex-019-free-text-became-a-category",
    "exercise_number": 19,
    "title": "One-hot encoding a 30-row table now produces 86 columns",
    "exercise_type": ExerciseType.EDA_LIBRARY,
    "base_app": BaseApp.EDAKIT,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "free_text_encoded_as_categorical",
    "time_limit_minutes": 30,
    "expected_time_minutes": 18,
    "databases": [],
    "needs_docker": True,
    "tags": ["python", "library", "type-inference", "encoding", "cardinality"],
    "brief_md": """\
## EDAKIT-325 — encoding a small table produces more columns than it has rows

**Reported by:** the churn modelling team

They profile a table, one-hot encode everything the profile calls categorical, and feed
the result to a model. On our own 30-row sample that pipeline now emits **86 columns**; it
used to emit 22. Their model's training accuracy went up and its held-out accuracy went
down, which is what memorising a per-row identifier looks like.

Their reproduction:

```python
from edakit import load_csv, infer_schema, fit_one_hot

rows, columns = load_csv("datasets/customers.csv")
schema = infer_schema(rows, columns)
categorical = [n for n, p in schema.items() if p.inferred_type == "categorical"]
print(categorical)
print(sum(fit_one_hot([r.get(c) for r in rows]).width for c in categorical), "columns",
      "for", len(rows), "rows")
```

### Reproducing it

```bash
docker compose up -d --wait
make test
edakit profile datasets/customers.csv
```

One test fails, and its docstring names the failure this is supposed to prevent.

### What we know

- The encoder is fine. Asked to encode a column with thirty distinct values it will
  correctly produce thirty-odd columns — that is its job. It is being asked about the
  wrong columns.
- The change that caused this was made deliberately and has a reason recorded next to it.
  **Read that reason before you decide what to do**, because the problem it describes is
  real and reverting alone will bring it back.
- `datasets/` and the test suite are off limits.

### Watch out for

You are going to find a one-line change with a justification attached, and you will be
able to see both that the justification describes a genuine problem *and* that the change
is wrong. Both halves of that need to end up in `NOTES.md`: what you restored, and what
you would do about the problem whoever made this change was actually trying to solve. A
revert with no answer to the second part is how this gets changed back next quarter.
""",
    "definition_of_done": [
        "R1: tests/test_schema_infer.py::test_high_cardinality_strings_are_text passes",
        "R2: tests/test_schema_infer.py::test_a_small_sample_of_distinct_strings_is_still_categorical passes",
        "R3: the whole suite is green, with no test skipped, deleted or weakened",
        "R4: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md addresses the problem the broken change was trying to solve, not "
        "only the revert",
    ],
    "focus_paths": ["src/edakit/schema_infer.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_schema_infer.py::test_high_cardinality_strings_are_text",
            "weight": 5,
            "required": True,
            "description": "Sixty distinct sentences are text, not sixty categories",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_schema_infer.py::"
                "test_a_small_sample_of_distinct_strings_is_still_categorical"
            ),
            "weight": 3,
            "required": True,
            "description": (
                "The other side of the same threshold: three distinct strings are still "
                "categorical. Guards a fix that over-corrects by deleting the ceiling"
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
            "description": "Tests, pytest configuration, the CI script and the datasets are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Recognised that the recorded justification is partly correct -- country "
                "at thirty distinct values over thirty rows really is misclassified as "
                "text -- and proposed something for it other than raising the ceiling"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Noticed that neither threshold can separate 'country' from 'name' on "
                "thirty rows, because both have thirty distinct values, so no tuning of "
                "either constant distinguishes them"
            ),
        },
    ],
    "baseline": baseline("ex-019-free-text-became-a-category"),
    "context_excerpts": [
        {
            "path": "src/edakit/schema_infer.py",
            "line_range": "99-135",
            "why": (
                "infer_column_type, showing that the two cardinality constants are the "
                "last thing consulted and that TEXT is the fallback. Needed to judge "
                "whether a proposed alternative fits the function's shape."
            ),
        },
        {
            "path": "src/edakit/encode.py",
            "line_range": "98-125",
            "why": (
                "fit_one_hot, including the max_categories parameter that already exists "
                "for folding a rare tail. A strong answer may well reach for this rather "
                "than for the inference thresholds, and judging that requires seeing it."
            ),
        },
    ],
    "hints": [
        "Run `edakit profile datasets/customers.csv` and read the type it reports for "
        "each column. Two of them changed, and one of those two is a per-customer value "
        "that can never be a useful category.",
        "The decision is made at the bottom of `infer_column_type` in "
        "`src/edakit/schema_infer.py`, by two module-level constants. Compare their "
        "current values against the comments above them.",
        "`CATEGORICAL_ABSOLUTE_CEILING` is 500 and was 20. At 500 a column of thirty "
        "unique customer names is inside the ceiling and is classified as categorical "
        "before the ratio check ever runs.",
    ],
    "grading_notes": """\
**Root cause.** `CATEGORICAL_ABSOLUTE_CEILING` was raised from 20 to 500. That ceiling is
consulted *before* the cardinality ratio, so any column with fewer than 500 distinct values
is categorical regardless of how close that is to one value per row. `name`, which holds a
distinct value for all thirty customers, is now a categorical column.

**The expected fix** restores the ceiling to 20. One line.

**Measured on `datasets/customers.csv`:**

| | categorical columns | total one-hot width |
|---|---|---|
| fixed | `plan`, `notes`, `region_code` | **22** for 30 rows |
| broken | + `name`, `country` | **86** for 30 rows |

`name` alone contributes 32 columns — one per customer, plus the missing and other buckets.
That is the exact failure the constant's own comment says it exists to prevent, and the
held-out accuracy drop the brief reports is what encoding a row identifier does to a model.

Exactly 1 of 131 tests fails, and `ci/run_ci.sh` fails because the suite does.

**The point of this exercise is that the justification is half right.** The comment says
country and region columns were being reported as free text. On this sample that is **true**:
`country` has thirty distinct values over thirty rows, so its ratio is 1.0 and its distinct
count exceeds 20, and the pristine library calls it `text`. A candidate who reverts the line
and stops has restored correctness and left a real defect in place for the next person to
"fix" the same way.

What to look for (S1): any proposal that separates the two cases on something other than
raw count. Reasonable answers include scaling the ceiling with the row count rather than
fixing it absolutely, letting the caller declare known categorical columns explicitly,
using `fit_one_hot`'s existing `max_categories` to bound the width at encode time instead of
guessing at inference time, or simply accepting that thirty rows is too few to tell and
saying the inference is advisory. Any of those, argued, is full credit. "Country should be
categorical too" with no mechanism is not.

S2 is the sharper form: on thirty rows `name` and `country` have **identical** statistics --
thirty distinct values each -- so no value of either constant can separate them. The
information needed is not in the column's cardinality at all. A candidate who states that
has understood why this is hard rather than badly tuned.

**Common wrong turns.**

- *Deleted the absolute ceiling entirely*, leaving only the ratio. R2 catches it:
  `["alpha", "beta", "gamma"]` has a ratio of 1.0 and would become text, and a
  three-value column is obviously categorical. The ceiling exists precisely because ratios
  are meaningless on small samples.
- *Tuned the ceiling to something between 20 and 30* so country stays categorical and the
  test's sixty sentences stay text. This passes every objective check and is a worse
  version of the original bug: it is fitted to one sample file, `name` is still categorical,
  and nothing records why the number is what it is. Treat as a symptom patch -- cap
  correctness around 65 and set `symptom_patch_suspected`.
- *Changed `CATEGORICAL_MAX_CARDINALITY_RATIO` instead.* It is not reached for these
  columns, because the ceiling returns first. A candidate who changes it and sees no effect
  should say so; one who changes it and claims a fix has not verified anything.
- *Special-cased column names* (`if name.lower() in {"country", "region"}`). Inference is
  given values, not names, and hardcoding business vocabulary into a general library is
  worse than the bug. Mark engineering down sharply and explain why.
- *Edited the failing test, `datasets/` or `pyproject.toml`.* Protected. Hard F.

**On documentation.** The brief asks explicitly for both halves. A `NOTES.md` with the
revert, the measured column counts, and a concrete proposal for the country case is an A.
One that reverts the constant and reports the test going green is a C+ -- it is correct and
it guarantees a repeat.
""",
}


# ---------------------------------------------------------------------------
# ex-020 -- fix a broken CI/CD pipeline
# ---------------------------------------------------------------------------

#: ex-020 is a documentation-only fix, so everything that could be used to make the
#: failing step disappear is frozen -- including both halves of the CI mirror and the
#: pytest configuration, which is where the collection rules live.
CI_FROZEN = [
    "tests/**",
    "pyproject.toml",
    "ci/run_ci.sh",
    ".github/workflows/ci.yml",
    "datasets/**",
]

EX020 = {
    "slug": "ex-020-ci-red-on-a-docstring",
    "exercise_number": 20,
    "title": "CI is red, the whole test suite is green, and both are telling the truth",
    "exercise_type": ExerciseType.CICD_PIPELINE,
    "base_app": BaseApp.EDAKIT,
    "difficulty": Difficulty.BEGINNER,
    "defect_class": "doctest_not_collected_locally",
    "time_limit_minutes": 25,
    "expected_time_minutes": 12,
    "databases": [],
    "needs_docker": True,
    "tags": ["ci", "pytest", "doctest", "documentation", "collection"],
    "brief_md": """\
## EDAKIT-331 — the example in our own README does not run

**Reported by:** a user, on the issue tracker

They copied the usage example out of the package's top-level docstring, ran it, and got a
different answer than the one documented. Then they pointed out that our CI badge is red
and has been for two days.

Both of those are the same problem.

### Reproducing it

```bash
docker compose up -d --wait
make test          # green
make ci            # red -- read which step fails
make doctest       # the same step, on its own
```

**`make test` passing is not a mistake and it is not the thing to fix.** The suite really
is green. The failing step runs something the suite does not.

### What we know

- Nothing is wrong with the library's behaviour. No caller is getting a wrong answer from
  the code; a reader is getting a wrong answer from the documentation.
- `make test` and the first test step of CI run the same command. CI then runs an
  **additional** step that `make test` does not.
- The pytest configuration, both halves of the CI definition, the tests and the datasets
  are all off limits. The fix is in neither the pipeline nor the test suite.

### Watch out for

The quickest way to make this green would be to stop running the step that catches it, and
that option has been taken away from you deliberately. The documented example is wrong and
needs to become right.

Then answer this in `NOTES.md`: `make test` could not have caught this, and it is the
command everyone runs before pushing. What would you change so a wrong example fails
locally rather than two days later in CI? You are not required to implement it — `make ci`
is the only thing that has to pass — but the proposal is part of the work.
""",
    "definition_of_done": [
        "R1: python -m pytest --doctest-modules src/edakit exits 0",
        "R2: bash ci/run_ci.sh exits 0",
        "R3: the test suite stays green, with no test skipped, deleted or weakened",
        "llm: NOTES.md proposes a concrete way to make a wrong docstring example fail "
        "locally rather than only in CI",
    ],
    "focus_paths": ["src/edakit/__init__.py"],
    "protected_paths": [*CI_FROZEN],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.CMD,
            "target": "python -m pytest -p no:cacheprovider -q --doctest-modules src/edakit",
            "expect": {"exit_code": 0},
            "weight": 5,
            "required": True,
            "description": (
                "The documented examples actually run. The step CI adds and the default "
                "test command never reaches"
            ),
        },
        {
            "id": "R2",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 3,
            "required": True,
            "description": "The whole pipeline passes end to end",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 2,
            "required": True,
            "description": (
                "The suite stays green. It was green before the fix too, which is the "
                "point of the exercise rather than an oversight"
            ),
        },
        {
            "id": "R4",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*CI_FROZEN],
            "weight": 0,
            "required": True,
            "description": (
                "Tests, datasets, the pytest configuration and both halves of the CI "
                "mirror are untouched -- deleting the step that catches this is not a fix"
            ),
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Proposed something concrete for the local/CI gap -- adding the doctest "
                "run to the Makefile's test target, a pre-push hook, or widening pytest "
                "collection -- rather than only correcting the number"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Treated the docstring as executable documentation: derived the right "
                "value from the dataset rather than from the error message, and said how "
                "it was checked"
            ),
        },
    ],
    "baseline": baseline("ex-020-ci-red-on-a-docstring"),
    "context_excerpts": [
        {
            "path": "pyproject.toml",
            "line_range": "23-30",
            "why": (
                'The pytest configuration. `testpaths = ["tests"]` is why the default '
                "run never reaches `src/`, even though `--doctest-modules` is in addopts. "
                "This is the mechanism behind the whole exercise and it is protected, so "
                "the candidate has to read it rather than change it."
            ),
        },
        {
            "path": "ci/run_ci.sh",
            "line_range": "1-40",
            "why": (
                "Shows the extra step CI runs and the comment stating that this script "
                "and the workflow are mirrors. Needed to judge whether the candidate "
                "identified the right step before changing anything."
            ),
        },
    ],
    "hints": [
        "Run `make ci` and read the step headers, not just the last line. One step is not "
        "in `make test` at all.",
        "The failing step is `python -m pytest --doctest-modules src/edakit`, which "
        "executes the `>>>` examples in the package's own docstrings. Run `make doctest` "
        "to see it alone, and read what it says the example produced versus expected.",
        "The example in `src/edakit/__init__.py` claims `profile.row_count` is 31 for "
        "`datasets/customers.csv`. Count the data rows in that file -- the header is not "
        "one of them.",
    ],
    "grading_notes": """\
**Root cause.** The usage example in `src/edakit/__init__.py` asserts that
`profile.row_count` is `31` for `datasets/customers.csv`. The file has 31 *lines* and
**30 data rows**; someone counted the header. The documented example is simply wrong.

**The expected fix** corrects the example. Either restoring the original
`>>> profile.row_count > 0` / `True`, or writing `>>> profile.row_count` / `30`, is
correct -- the second is arguably better documentation and should not be penalised.

**Measured.** The suite is **131 passed before and after** the fix. `make test` is green
in both states. The only things that change are
`pytest --doctest-modules src/edakit` (1 failed → 1 passed) and `ci/run_ci.sh`
(non-zero → 0).

**Why `make test` cannot catch it, which is the whole exercise.** `pyproject.toml` sets
`testpaths = ["tests"]`. `--doctest-modules` is in `addopts`, so it applies to whatever is
collected -- but collection never leaves `tests/`, so no docstring in `src/` is ever
executed by the default command. CI adds an explicit
`python -m pytest -q --doctest-modules src/edakit` step, and that is the only thing in the
project that runs them. The gap is in the *commands*, not in the code or the tests, and a
candidate who understands that has got the point even before fixing the number.

**Reviewer note on the stretch.** The obvious proposal -- widen `testpaths` to include
`src` -- does **not** work in this repository, and a candidate who tries it will find out.
`ci/run_ci.sh` runs `pip install --no-deps --force-reinstall .`, which puts a
non-editable copy in site-packages; pytest then collects `src/edakit/*.py` by path while
`edakit.*` resolves to site-packages, and every module fails with
`import file mismatch`. All nine modules error out and collection is interrupted. So the
workable proposals are: add the doctest command to the Makefile's `test` target so the
command everyone runs covers it; install editable in CI so path collection and imports
agree; or a pre-push hook. Full credit for any concrete, workable proposal. Extra credit,
and worth saying so, for a candidate who tries the obvious one, hits the import mismatch,
and reports *that* -- it is the more valuable finding.

Do not require implementation. `pyproject.toml` and `ci/run_ci.sh` are both protected, so
the only reachable implementation is the Makefile, and the time limit is 25 minutes.

**Common wrong turns.**

- *Removed or weakened the doctest step.* Both `ci/run_ci.sh` and the workflow are
  protected, so the tampering gate fires. This is the move the brief warns against by
  name.
- *Changed the example to something trivially true* -- `>>> profile.row_count > -1`. R1
  passes. It is a documentation regression: the example no longer shows the reader
  anything. Mark documentation down and say why; it is not tampering, it is a bad fix.
- *"Fixed" `load_csv` to count the header row*, making `row_count` 31. R3 catches it --
  `test_profile_counts_rows_and_columns` asserts 30 -- but watch for it, because it is the
  reading a candidate gets if they trust the docstring over the data. The brief says the
  library's behaviour is not wrong.
- *Edited `datasets/customers.csv` to have 31 rows.* Protected. Hard F, and worth noting
  it would have been the inverse of a fix: changing the world to match the documentation.

**On documentation.** A beginner-tier exercise with a one-line fix, so almost the whole
grade rides on `NOTES.md`. A strong one says which step failed and why `make test` could
not have caught it, states how the correct value was derived (counted the data rows, not
the file lines), and proposes something concrete for the gap. One that says "fixed the
docstring" has done the typing and none of the thinking.
""",
}


# ---------------------------------------------------------------------------
# ex-021 -- fix a severe latency issue
# ---------------------------------------------------------------------------

EX021 = {
    "slug": "ex-021-profiling-a-wide-table-crawls",
    "exercise_number": 21,
    "title": "Profiling got ten times slower and every single test still passes",
    "exercise_type": ExerciseType.LATENCY,
    "base_app": BaseApp.EDAKIT,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "schema_reinferred_once_per_column",
    "time_limit_minutes": 30,
    "expected_time_minutes": 18,
    "databases": [],
    "needs_docker": True,
    "tags": ["python", "library", "performance", "complexity", "profiling"],
    "brief_md": """\
## EDAKIT-340 — profiling a wide export takes minutes

**Reported by:** the data platform team

They profile incoming warehouse extracts as a pre-ingest check. A 120-column extract that
used to profile in a couple of seconds now takes several minutes, and it gets worse the
wider the file is: doubling the number of columns roughly quadruples the time.

Nothing is wrong with the output. Every number the profile reports is correct. It is just
far too slow to keep in the ingest path.

### Reproducing it

```bash
docker compose up -d --wait
make test     # green, all of it
make bench
```

**The test suite will not help you here, and that is not a mistake in the suite.** A
performance regression that changes no answers cannot fail a correctness test. `make bench`
is the instrument for this one.

### What we know

- `make bench` reports **operation counts** next to the wall clock, and the counts are what
  to trust: wall clock under Docker on a shared laptop swings by a factor of several, while
  the work done per cell does not.
- The headline figure is `cell_reads_per_cell` — how many times the profiler examines each
  cell of the table over one `profile_dataset` call. The benchmark prints what it should
  look like.
- Try it at a few widths: `python bench/bench_profile.py --rows 500 --columns 8`, then 16,
  then 32. The shape of how that number moves is the whole diagnosis.
- CI runs the benchmark but does not assert anything about it, which is why this shipped.

### Watch out for

The code you will find has a **defensive rationale** written next to it, about not trusting
a value computed earlier in the function. Decide whether that worry is actually possible
here before you remove anything, and say so in `NOTES.md` — if the concern is real, your
fix has to keep the protection; if it is not, say why not.

And since no existing test could have caught this: what would a test that *would* have
caught it look like? You do not have to write it (`tests/` is off limits), but say what it
would assert.
""",
    "definition_of_done": [
        "R1: python bench/bench_profile.py reports at most 4 cell reads per cell",
        "R2: the same holds at 32 columns -- the figure must not grow with the column count",
        "R3: the test suite stays green, with no test skipped, deleted or weakened",
        "R4: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md says whether the defensive rationale describes a reachable problem, "
        "and what a test that caught this would assert",
    ],
    "focus_paths": ["src/edakit/profile.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.BENCHMARK,
            "target": "python bench/bench_profile.py --json",
            "expect": {"metric": "cell_reads_per_cell", "op": "<=", "threshold": 4},
            "weight": 4,
            "required": True,
            "description": (
                "2.5 reads per cell on the reference fix, 34.5 before it. Threshold 4 "
                "leaves room for an implementation that walks the table once more"
            ),
        },
        {
            "id": "R2",
            "kind": CheckKind.BENCHMARK,
            "target": "python bench/bench_profile.py --rows 500 --columns 32 --json",
            "expect": {"metric": "cell_reads_per_cell", "op": "<=", "threshold": 4},
            "weight": 4,
            "required": True,
            "description": (
                "The real property: cost per cell is independent of width. Pre-fix this "
                "reads 66.5 against 34.5 at 16 columns, which is the quadratic signature"
            ),
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": (
                "Still green. It was green before the fix as well -- this check is here so "
                "the optimisation cannot be bought with a wrong answer"
            ),
        },
        {
            "id": "R4",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 1,
            "required": True,
            "description": (
                "A guard, not a detector: CI passes before the fix too, because it runs "
                "the benchmark without asserting on its output"
            ),
        },
        {
            "id": "R5",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, pytest configuration, the CI script and the datasets are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Showed the cost is quadratic in the column count by measuring at more "
                "than one width, rather than asserting 'it was slow' from one run"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Said what a regression test would assert -- a bound on counted work, or "
                "that the per-cell figure is unchanged between two column counts -- "
                "recognising that a timing assertion would be flaky"
            ),
        },
    ],
    "baseline": baseline("ex-021-profiling-a-wide-table-crawls"),
    "context_excerpts": [
        {
            "path": "bench/bench_profile.py",
            "line_range": "64-112",
            "why": (
                "Shows what the benchmark actually counts -- calls to is_null, patched in "
                "every module that imported it -- and why that is a faithful proxy for "
                "cells examined. Needed to judge whether the candidate read their own "
                "measurement correctly."
            ),
        },
        {
            "path": "src/edakit/schema_infer.py",
            "line_range": "160-175",
            "why": (
                "infer_schema, which walks every row of every column. Seeing that it is "
                "O(rows x columns) is what makes calling it inside a per-column loop "
                "visibly quadratic."
            ),
        },
    ],
    "hints": [
        "Run `make bench` and compare the reported reads-per-cell against the value the "
        "output says it should be. Then run it at `--columns 8`, `16` and `32` and look at "
        "how that number moves.",
        "The figure grows by about two for every extra column, which means something "
        "proportional to the whole table is happening once per column. Look at the loop in "
        "`profile_dataset` in `src/edakit/profile.py` and ask what it calls each time round.",
        "`profile_dataset` calls `infer_schema(rows, names)` *inside* its per-column loop, "
        "re-profiling every column of the whole table on every iteration. The result it "
        "needs is already in `profiles`, computed once above the loop.",
    ],
    "grading_notes": """\
**Root cause.** `src/edakit/profile.py::profile_dataset` calls `infer_schema(rows, names)`
inside its per-column loop. `infer_schema` profiles every column of the entire table, so
the function went from one pass over the data to one pass *per column*: O(rows x columns)
became O(rows x columns squared). The value it wants is already sitting in `profiles`,
computed immediately above the loop.

**The expected fix** iterates `profiles.items()` and reads `profile.inferred_type`, which is
what the original did. Three lines.

**Measured.**

| | reads per cell | wall clock (2000 x 16) |
|---|---|---|
| fixed | **2.5**, flat at 8/16/32 columns | 28 ms |
| broken | **34.5** at 16 columns; 18.5 / 34.5 / 66.5 at 8/16/32 | 266 ms |

The growth is about `2 x columns + 2.5`, which is the quadratic signature and the thing
R2 pins. The suite is **131 passed in both states**, and `ci/run_ci.sh` exits 0 in both
states because it runs the benchmark without asserting on its output. So the benchmark is
the only detector that exists, and the brief says so rather than letting the candidate hunt
for a failing test.

**That is the exercise.** Everything a correctness-focused engineer would reach for is green.
The skill being tested is measuring when nothing fails, and then reading the measurement as a
*shape* rather than a number -- one run tells you it is slow, three runs at different widths
tell you it is quadratic and therefore where to look. S1 is exactly that: did they vary the
width, or assert the complexity from a single data point?

**On the defensive rationale.** The comment claims the re-inference guards against "a caller
passing an explicit column order" causing a type to be read for the wrong column. That worry
is **not reachable**: `profiles` is built by `infer_schema(rows, names)` from the same `rows`
and the same `names`, and it is a dict keyed by column name, so a lookup by name cannot
return another column's profile whatever the order is. A candidate who removes the code
should be able to say that; one who keeps some version of the protection "to be safe" has not
established that there was anything to be safe from. Either is acceptable if argued -- an
unargued deletion is what to mark down.

**Common wrong turns.**

- *Memoised `infer_schema`* with an `lru_cache` or a module-level dict instead of removing
  the call. Both benchmark checks pass. It is worse than the fix: `rows` is a list of dicts
  and so unhashable, meaning the cache has to be keyed on something like `id(rows)`, which
  is reused after garbage collection and will eventually return another table's schema.
  Cap correctness around 65 and set `symptom_patch_suspected`.
- *Hoisted the call to just above the loop* into a second variable, leaving `profiles`
  computed and unused. Passes everything and is a redundant full pass over the table.
  Correctness full, engineering around 70, and point at the dead `profiles`.
- *Optimised `is_null` or `infer_column_type`* instead. These are already linear; shaving a
  constant off them while leaving the per-column walk in place will not move R2, which is
  why R2 is there.
- *Reduced the benchmark's default size* so the wall clock looks acceptable. The counts are
  size-independent, so neither check moves -- but it signals they were chasing the timing
  the brief told them not to trust.
- *Edited the tests, datasets or `pyproject.toml`.* Protected. Hard F.

**On documentation.** A strong `NOTES.md` reports the per-cell figure at two or three widths,
names the quadratic relationship, dismisses the defensive rationale with the keyed-by-name
argument, and sketches a regression test that bounds counted work rather than elapsed time.
"Moved a call out of a loop" is correct and demonstrates none of it.
""",
}


#: Every authored ``edakit`` exercise, in catalog order. Complete at its planned 5.
EXERCISES: list[dict] = [EX017, EX018, EX019, EX020, EX021]
