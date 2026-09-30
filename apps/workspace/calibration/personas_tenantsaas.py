"""Calibration personas for the ``tenantsaas`` exercises.

Each exercise's own ``grading_notes`` already enumerate the expected fix and the
plausible wrong approaches under "Watch for". Those lists are the source for the
personas here, so the corpus probes the failure modes the author actually anticipated
rather than ones invented for the occasion.

Every exercise gets three tiers:

* ``root-cause`` -- the reference fix, committed cleanly, with a real writeup. The
  upper anchor. If the rubric will not give this an A-minus-or-better, it is harsh.
* ``silent`` -- byte-for-byte the same code fix, one terse commit, NOTES.md left as the
  untouched template. Isolates the documentation weight: the only variable between this
  and ``root-cause`` is the writeup, so the gap between their letters *is* the rubric's
  answer to "how much is explaining your work worth".
* a green-but-wrong tier -- passes acceptance checks while being work no reviewer would
  accept. The most valuable probe in the set, because it is the case automated grading
  fails at: the objective signal says solved, and only judgment says otherwise. The
  ``min(objective, model)`` reconciliation cannot help here, since the objective score
  is the high one.
"""

from __future__ import annotations

from apps.workspace.calibration.spec import Commit, Edit, Persona

# ---------------------------------------------------------------------------
# ex-005 -- CI red after a test reorg
#
# Two defects: both CI files select the security and perf suites by directory
# (tests/security/, tests/perf/) instead of by marker (-m security, -m perf), and the
# workflow pins python-version 3.9 against a codebase using PEP 604 unions.
# ---------------------------------------------------------------------------

_EX005_SELECTOR_EDITS = (
    Edit(
        path="ci/run_ci.sh",
        find="python -m pytest -p no:cacheprovider -q tests/security/",
        replace="python -m pytest -p no:cacheprovider -q -m security",
    ),
    Edit(
        path="ci/run_ci.sh",
        find="python -m pytest -p no:cacheprovider -q tests/perf/",
        replace="python -m pytest -p no:cacheprovider -q -m perf",
    ),
    Edit(
        path=".github/workflows/ci.yml",
        find="run: python -m pytest -p no:cacheprovider -q tests/security/",
        replace="run: python -m pytest -p no:cacheprovider -q -m security",
    ),
)

_EX005_RUNTIME_EDIT = Edit(
    path=".github/workflows/ci.yml",
    find='python-version: "3.9"',
    replace='python-version: "3.12"',
)

_EX005_ROOT_CAUSE_NOTES = """\
# Engineering notes

## Diagnosis

`make test` is green and `make ci` is red, which is the whole clue: the difference is
not the tests, it is how CI selects them. Running `bash ci/run_ci.sh` fails at the
"Running the security suite" step with `ERROR: file or directory not found:
tests/security/`, and pytest exits 4 there -- a usage error, not a test failure. With
`set -euo pipefail` at the top of the script, exit 4 ends the run.

## Root cause

Two separate defects, both landed in Tuesday's change.

1. `ci/run_ci.sh` and `.github/workflows/ci.yml` select the security and perf suites
   by *directory* (`tests/security/`, `tests/perf/`). Those directories have never
   existed. `pytest.ini` registers `security` and `perf` as **markers**, and the suites
   have always been selected with `-m security` / `-m perf`.
2. `.github/workflows/ci.yml` also pins `python-version: "3.9"`. `tenants/context.py`
   uses PEP 604 unions (`int | None`), which are a syntax error before 3.10, so the
   GitHub job cannot even import the app. This one is invisible locally -- the
   container runs 3.12 -- and is only findable by reading the workflow.

## The fix

Restored marker selection in both files and restored `python-version: "3.12"`. Three
lines in the script and two in the workflow. Nothing about the tests changed, because
nothing about the tests was wrong.

Both files, not one: `README.md` states that `ci.yml` and `ci/run_ci.sh` must change
together, and the merge gate runs the script while GitHub runs the workflow. Fixing
only the script would have turned the pipeline green locally while leaving GitHub
broken -- the exact state we were already in, reversed.

## Why this fix and not the alternatives

I considered creating `tests/security/` and `tests/perf/` and moving the marked tests
into them, which would also make CI green. Rejected: it contradicts `pytest.ini`'s
marker registration, the markers would then be dead configuration, and it is a
refactor of the test layout during an outage with four PRs blocked. The smaller change
that restores the documented convention is the right one under these circumstances.

I also considered dropping the two extra steps, since `python -m pytest -q` already
runs every test including the marked ones, so the separate steps add no coverage.
Rejected: they exist as *named gates*, so a security regression fails a step called
"Running the security suite" rather than being one line in a 400-test summary. Removing
a security gate to fix a selector bug would be a silent downgrade of the pipeline.

## What I verified

- `bash ci/run_ci.sh` exits 0, and the security and perf steps each report collected
  tests rather than zero.
- `python -m pytest -q` still passes with nothing skipped or deselected.
- `grep -rn "tests/security\\|tests/perf" ci/ .github/` returns nothing.
- Diffed the workflow against the script step by step to confirm they now agree.

I could not verify the Python pin the way I verified the rest, because there is no
GitHub runner here. I confirmed the failure mode instead: `python3.9 -c "import ast;
ast.parse(open('tenants/context.py').read())"` is a syntax error, and 3.12 parses it.

## Risks and follow-ups

Low risk: no application code changed. The residual risk is the one that caused this
outage -- the two files can still drift, because nothing enforces that they agree.

## What I'd do with more time

Stop maintaining the duplication. In order of preference:

1. **Make the workflow call the script.** Replace the three duplicated pytest steps in
   `ci.yml` with `run: bash ci/run_ci.sh`. One definition of the pipeline, so drift is
   structurally impossible. Costs the per-step granularity in the GitHub UI, which is
   the only reason not to do it.
2. **Assert they agree.** A test that parses the `run:` lines out of `ci.yml` and the
   `python -m pytest` lines out of `run_ci.sh` and asserts the two lists are equal.
   Cheap, keeps the granularity, and fails on the PR that introduces the drift rather
   than after it merges. This is what I would actually open a PR for tomorrow.
3. **Generate one from the other** at build time. Strongest guarantee, most machinery;
   only worth it if the pipeline grows.

Separately, `-m security` silently passes when it matches zero tests, so deleting every
security test would keep CI green. `--strict-markers` plus asserting a non-zero
collected count would close that hole.
"""

_EX005_SUPPRESSED_NOTES = """\
# Engineering notes

## Diagnosis

CI was failing on the security and perf steps. `make test` passes, so the tests are
fine -- it was the pipeline.

## Root cause

The security and perf steps were pointing at test paths that do not resolve, so pytest
returned a non-zero exit and `set -e` killed the run.

## The fix

Pointed the two steps back at the markers and made them non-blocking with `|| true` so
a selector problem can never take the whole pipeline down again. Also bumped the
workflow's Python version to 3.12 to match the container.

## Why this fix and not the alternatives

The full `python -m pytest -q` step already runs every test in the repo, including the
ones marked `security` and `perf`, so those two steps are duplicate coverage. Making
them non-blocking keeps the reporting without letting them block merges. Four PRs were
blocked and the priority was unblocking the team.

## What I verified

`bash ci/run_ci.sh` exits 0 and the full suite is green.

## Risks and follow-ups

Low. No application code changed.

## What I'd do with more time

Look at whether the two steps are worth keeping at all given the full suite covers
them.
"""

EX005_ROOT_CAUSE = Persona(
    persona_id="root-cause",
    exercise_slug="ex-005-ci-red-after-test-reorg",
    tier="Both defects fixed at the root cause, clean commits, thorough writeup",
    rationale=(
        "The upper anchor. Matches the author's reference patch exactly, fixes both "
        "files and the runtime pin, and proposes three concrete drift-prevention "
        "mechanisms (the stretch goal S1). If this does not land at A- or better the "
        "rubric is too harsh, and every letter below it is compressed."
    ),
    predicted_letter="A",
    notes_md=_EX005_ROOT_CAUSE_NOTES,
    commits=(
        Commit(
            at_minute=6,
            message=(
                "fix(ci): select the security and perf suites by marker, not directory\n"
                "\n"
                "Tuesday's change switched both CI files from `-m security` / `-m perf`\n"
                "to `tests/security/` / `tests/perf/`. Those directories have never\n"
                "existed -- pytest.ini registers the two suites as markers. pytest\n"
                "exits 4 on an unresolvable path, which is a usage error rather than a\n"
                "test failure, and `set -euo pipefail` turns that into a red pipeline.\n"
                "\n"
                "This is why `make test` was green while `make ci` was red: the tests\n"
                "were never the problem.\n"
                "\n"
                "Changed in ci/run_ci.sh and .github/workflows/ci.yml together, as\n"
                "README.md requires -- the merge gate runs the script, GitHub runs the\n"
                "workflow, and fixing one would have left the other broken."
            ),
            edits=_EX005_SELECTOR_EDITS,
        ),
        Commit(
            at_minute=12,
            message=(
                "fix(ci): restore python 3.12 in the workflow\n"
                "\n"
                'Tuesday also pinned python-version: "3.9". tenants/context.py uses PEP\n'
                "604 unions (`int | None`), a syntax error before 3.10, so the GitHub\n"
                "job could not import the app at all.\n"
                "\n"
                "Not reproducible locally -- the container runs 3.12 -- so this is only\n"
                "findable by reading the workflow rather than by running the script."
            ),
            edits=(_EX005_RUNTIME_EDIT,),
        ),
        Commit(
            at_minute=16,
            message=(
                "docs: write up the CI outage and how to stop the two files drifting\n"
                "\n"
                "Records both defects, why only one of them is reproducible locally, and\n"
                "the options for removing the duplication between ci.yml and\n"
                "run_ci.sh -- having the workflow call the script, or a test asserting\n"
                "their step lists match."
            ),
            edits=(Edit(path="NOTES.md", content=_EX005_ROOT_CAUSE_NOTES),),
        ),
    ),
    fraction_time_used=0.68,
)

EX005_SILENT = Persona(
    persona_id="silent",
    exercise_slug="ex-005-ci-red-after-test-reorg",
    tier="Identical correct fix, one terse commit, NOTES.md untouched",
    rationale=(
        "The documentation probe. The code is byte-for-byte identical to root-cause, so "
        "correctness and completeness should score the same and the entire letter gap "
        "is the rubric's price for not explaining your work. The system prompt says an "
        "undocumented working change should be about 90 correctness and 30 "
        "documentation, which lands near C+/B-; the question is whether that matches "
        "what a human would give, and whether the gap from root-cause is credible."
    ),
    predicted_letter="C+",
    notes_md="",
    commits=(
        Commit(
            at_minute=11,
            message="fix ci",
            edits=(*_EX005_SELECTOR_EDITS, _EX005_RUNTIME_EDIT),
        ),
    ),
    fraction_time_used=0.44,
)

EX005_SUPPRESSED = Persona(
    persona_id="suppressed",
    exercise_slug="ex-005-ci-red-after-test-reorg",
    tier="Green by suppression: `|| true` on both suite steps",
    rationale=(
        "The green-but-wrong probe, and the highest-value item in the set. Every "
        "required check passes -- R1 exits 0, R3 finds no directory reference because "
        "the markers were restored, R4 sees 3.12, and the suite is untouched -- while "
        "the two security and perf gates have been made structurally incapable of "
        "failing. min(objective, model) offers no protection here because the objective "
        "score is the high one; only the model's judgment can catch it. The NOTES.md "
        "argues the steps are redundant, which is true of coverage and false of "
        "gating, so the model has to reason rather than pattern-match. If this scores "
        "anywhere near root-cause, the rubric cannot tell a fix from a cover-up."
    ),
    predicted_letter="D",
    notes_md=_EX005_SUPPRESSED_NOTES,
    commits=(
        Commit(
            at_minute=5,
            message=(
                "ci: stop the security and perf steps blocking the pipeline\n"
                "\n"
                "Selector was pointing at paths that do not exist. Restored the markers\n"
                "and added || true so these steps cannot take CI down again. The full\n"
                "pytest run already covers the same tests."
            ),
            edits=(
                Edit(
                    path="ci/run_ci.sh",
                    find="python -m pytest -p no:cacheprovider -q tests/security/",
                    replace="python -m pytest -p no:cacheprovider -q -m security || true",
                ),
                Edit(
                    path="ci/run_ci.sh",
                    find="python -m pytest -p no:cacheprovider -q tests/perf/",
                    replace="python -m pytest -p no:cacheprovider -q -m perf || true",
                ),
                Edit(
                    path=".github/workflows/ci.yml",
                    find="run: python -m pytest -p no:cacheprovider -q tests/security/",
                    replace=("run: python -m pytest -p no:cacheprovider -q -m security || true"),
                ),
            ),
        ),
        Commit(
            at_minute=9,
            message="ci: match the container's python version",
            edits=(_EX005_RUNTIME_EDIT,),
        ),
        Commit(
            at_minute=12,
            message="docs: notes on the CI fix",
            edits=(Edit(path="NOTES.md", content=_EX005_SUPPRESSED_NOTES),),
        ),
    ),
    fraction_time_used=0.52,
)

EX005_PERSONAS = (EX005_ROOT_CAUSE, EX005_SILENT, EX005_SUPPRESSED)


# ---------------------------------------------------------------------------
# ex-001 -- invoices drop the final day
#
# `billing/services.py::line_items_for_period` compares a DateTimeField against
# `date` bounds with `created_at__lt=period_end`, so the database coerces the bound to
# midnight and the final day is excluded. A single-day period becomes an empty range.
# ---------------------------------------------------------------------------

_EX001_BROKEN_FILTER = """\
    return LineItem.objects.filter(
        tenant_id=tenant_id,
        created_at__gte=period_start,
        created_at__lt=period_end,
    )"""

_EX001_FIXED_FILTER = """\
    # __date__gte / __date__lte, not a raw datetime comparison. created_at is a
    # timestamp while the period bounds are dates; comparing them directly makes
    # Postgres coerce the date to midnight, which silently drops everything
    # recorded on the final day of the period.
    return LineItem.objects.filter(
        tenant_id=tenant_id,
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
    )"""

_EX001_CONTRACT_TEST = '''\
"""Contract tests for the inclusive billing period.

Added after INC-2291. `test_billing.py` covers the reported symptom; these pin the
*rule* the symptom violated, so a future refactor that reintroduces a datetime-versus-
date comparison fails here with a message about the contract rather than about one
fixture row.
"""

from datetime import date

import pytest

from billing.models import LineItem
from billing.services import line_items_for_period
from tests.conftest import utc

pytestmark = pytest.mark.django_db


def test_the_last_minute_of_the_final_day_is_billed(acme, acme_project):
    """The period is inclusive, so 23:59 on the closing date is inside it."""
    item = LineItem.objects.create(
        tenant=acme,
        project=acme_project,
        kind=LineItem.Kind.API_CALL,
        description="Usage at 23:59 on the final day",
        amount_cents=100,
        created_at=utc(2026, 3, 31, 23, 59),
    )
    billed = line_items_for_period(acme.pk, date(2026, 3, 1), date(2026, 3, 31))
    assert item.pk in {billed_item.pk for billed_item in billed}


def test_the_first_minute_of_the_first_day_is_billed(acme, acme_project):
    """Inclusive at the lower bound too, which the original bug happened to get right."""
    item = LineItem.objects.create(
        tenant=acme,
        project=acme_project,
        kind=LineItem.Kind.API_CALL,
        description="Usage at 00:00 on the opening day",
        amount_cents=100,
        created_at=utc(2026, 3, 1, 0, 0),
    )
    billed = line_items_for_period(acme.pk, date(2026, 3, 1), date(2026, 3, 31))
    assert item.pk in {billed_item.pk for billed_item in billed}


def test_a_single_day_period_is_not_an_empty_range(acme, acme_project):
    """period_start == period_end must mean one whole day, not zero seconds.

    This is the case the midnight coercion turned into `[midnight, midnight)`.
    """
    item = LineItem.objects.create(
        tenant=acme,
        project=acme_project,
        kind=LineItem.Kind.API_CALL,
        description="Single-day usage",
        amount_cents=100,
        created_at=utc(2026, 3, 10, 16, 45),
    )
    billed = line_items_for_period(acme.pk, date(2026, 3, 10), date(2026, 3, 10))
    assert item.pk in {billed_item.pk for billed_item in billed}


def test_the_day_after_the_period_is_not_billed(acme, acme_project):
    """The inclusive fix must not widen the period by a whole day."""
    LineItem.objects.create(
        tenant=acme,
        project=acme_project,
        kind=LineItem.Kind.API_CALL,
        description="Usage just after the period closes",
        amount_cents=100,
        created_at=utc(2026, 4, 1, 0, 1),
    )
    billed = line_items_for_period(acme.pk, date(2026, 3, 1), date(2026, 3, 31))
    assert billed.count() == 0
'''

_EX001_ROOT_CAUSE_NOTES = """\
# Engineering notes

## Diagnosis

`tests/test_billing.py::test_period_includes_items_on_the_final_day` fails: the 23:30
item on 31 March is absent from a 1-31 March period. The single-day case is worse --
`period_start == period_end` returns nothing at all. Both point at the period filter
rather than at the metering data, and `make psql` confirms the rows are in the table.

Django also emits a `RuntimeWarning` about a naive datetime during the run, which is
the tell.

## Root cause

`billing/services.py::line_items_for_period` filtered

    created_at__gte=period_start, created_at__lt=period_end

`created_at` is a `DateTimeField`; `period_start` and `period_end` are `date` objects.
Comparing the two makes the database coerce each bound to **midnight**, so:

* `__lt=period_end` excludes everything recorded on the final day -- all 24 hours of
  it, not an edge case at 23:59.
* a single-day period becomes the empty half-open range `[midnight, midnight)`.

The bug is the type mismatch, not the operator. `__lte` alone would still be wrong: it
would admit exactly the one instant of midnight on the final day.

## The fix

Compare dates against dates: `created_at__date__gte` / `created_at__date__lte`. This
states the inclusive rule in the same terms `ARCHITECTURE.md` and
`Invoice.period_end.help_text` use, and it is the same form
`reporting.models_q_for_period` already uses for the annotation path, so the two
period definitions now agree.

The alternative -- keeping `__lt` and converting `period_end` to an aware end-of-day
datetime -- is also correct, but it leaves the reader to verify a conversion instead of
reading the rule off the query.

I restored the comment explaining the coercion. It had been deleted, and it is the
comment that would have prevented this.

## Why this fix and not the alternatives

Rejected `created_at__lt=period_end + timedelta(days=1)`. It makes every test pass
while leaving the timestamp-versus-date confusion in the code, so the next person to
touch this hits the same trap, and the query no longer says what the contract says. It
is the change I would have made if I only wanted green tests.

Rejected filtering in Python after the query: correct numbers, but it discards the
index and loads the whole table for a tenant.

Rejected redefining `period_end` as exclusive. That contradicts the brief and would
silently restate every historical invoice.

## What I verified

- The two named tests pass, plus the full suite (80 tests) with nothing skipped.
- `bash ci/run_ci.sh` exits 0.
- Added `tests/test_billing_period_contract.py`, four tests pinning the rule itself:
  last minute of the final day, first minute of the first day, the single-day period,
  and -- importantly -- that the day *after* the period is still excluded, which is
  what catches a fix that widens the bound by a day.
- Checked by hand that Acme's March total now includes the $17.50 overage.

## Answering Finance: can the totals be trusted?

**Not before this fix; yes after it, once March is re-run.** Concretely:

* The under-billing was **systematic, not sporadic** -- every invoice for every tenant
  lost its final day. It is not a subset of customers.
* The direction is one-way: customers were **under-billed**. No customer was ever
  charged for usage they did not have, so this is revenue we did not collect rather
  than money to refund.
* March can be re-run safely. `build_invoice` is idempotent
  (`test_build_invoice_is_idempotent`), so re-running recomputes totals against the
  same line items rather than double-counting.
* Anything already reconciled against a single-day query read zero and should be
  re-queried; that case returned nothing at all rather than being merely short.

## Risks and follow-ups

`created_at__date` applies the database's timezone conversion per row, so it cannot use
a plain index on `created_at`. At this table size that is not measurable, but if
billing gets slow, the fix is a functional index on `(tenant_id, (created_at AT TIME
ZONE 'UTC')::date)` -- not reverting to the datetime comparison.

I did not audit every other consumer of `line_items_for_period`; exports and reporting
both route through it, so they inherit the fix, but I have not proven nothing else
builds its own period filter.

## What I'd do with more time

1. Grep for other `__gte`/`__lt` pairs against `date` values -- `reporting/` has its own
   period helper and I would want to prove the two agree with a shared test rather than
   by reading them.
2. Add the backfill command Finance will need, so re-running March is one audited
   command rather than a shell loop.
3. Ask whether `LineItem.created_at` should be a `DateField` for billing purposes; the
   time of day has never mattered to an invoice, and the type mismatch would then be
   impossible.
"""

_EX001_WIDENED_NOTES = """\
# Engineering notes

## Diagnosis

The failing test showed the last day of the period was not being billed, and a
single-day period returned nothing.

## Root cause

The upper bound on the period filter was exclusive, so the final day fell outside the
range.

## The fix

Made the upper bound cover the whole final day by adding one day to `period_end` and
keeping the exclusive comparison:

    created_at__lt=period_end + timedelta(days=1)

That includes everything on the closing date and makes the single-day period work.

## Why this fix and not the alternatives

It is a one-line change and it keeps the existing `__gte` / `__lt` shape, so the query
is still a simple half-open range, which is the usual way to write these.

## What I verified

The two failing tests now pass, the full suite is green, and `bash ci/run_ci.sh` exits
0.

## Risks and follow-ups

Low -- the change is confined to one filter.

## What I'd do with more time

Add a test for the single-day case at a month boundary.
"""

EX001_ROOT_CAUSE = Persona(
    persona_id="root-cause",
    exercise_slug="ex-001-invoice-drops-final-day",
    tier="Date-typed comparison, new contract tests, writeup that answers Finance",
    rationale=(
        "The upper anchor for a SEV-2 under time pressure. Fixes the type mismatch "
        "rather than the operator, adds a test that specifically catches the widened-"
        "bound shortcut, and answers the question the brief actually asked -- whether "
        "the totals can be trusted -- which the grading notes single out as the "
        "difference between a good writeup and a code summary."
    ),
    predicted_letter="A",
    notes_md=_EX001_ROOT_CAUSE_NOTES,
    commits=(
        Commit(
            at_minute=7,
            message=(
                "fix(billing): compare dates to dates so the final day is billed\n"
                "\n"
                "line_items_for_period filtered created_at__gte / created_at__lt\n"
                "against date bounds. created_at is a DateTimeField, so the database\n"
                "coerced each bound to midnight: the exclusive upper bound dropped the\n"
                "entire final day of every period, and a single-day period collapsed to\n"
                "the empty range [midnight, midnight).\n"
                "\n"
                "Switched to created_at__date__gte / created_at__date__lte, which states\n"
                "the inclusive contract from ARCHITECTURE.md in the query itself and\n"
                "matches the form reporting.models_q_for_period already uses.\n"
                "\n"
                "Restored the comment explaining the coercion; it had been removed, and\n"
                "it is what would have prevented this.\n"
                "\n"
                "Refs INC-2291"
            ),
            edits=(
                Edit(
                    path="billing/services.py",
                    find=_EX001_BROKEN_FILTER,
                    replace=_EX001_FIXED_FILTER,
                ),
            ),
        ),
        Commit(
            at_minute=13,
            message=(
                "test(billing): pin the inclusive-period contract itself\n"
                "\n"
                "test_billing.py covers the reported symptom. These four cover the rule:\n"
                "the last minute of the final day, the first minute of the first day,\n"
                "the single-day period, and that the day after the period is still\n"
                "excluded.\n"
                "\n"
                "The last one is deliberate: it fails for a fix that widens the bound by\n"
                "a day, which is the shortcut that passes every existing test while\n"
                "leaving the date/datetime confusion in place."
            ),
            edits=(
                Edit(
                    path="tests/test_billing_period_contract.py",
                    content=_EX001_CONTRACT_TEST,
                ),
            ),
        ),
        Commit(
            at_minute=18,
            message=(
                "docs: write up INC-2291, including whether March can be trusted\n"
                "\n"
                "Records the root cause as a type mismatch rather than an operator\n"
                "choice, and answers Finance directly: systematic across all tenants,\n"
                "one-way under-billing, safe to re-run because build_invoice is\n"
                "idempotent."
            ),
            edits=(Edit(path="NOTES.md", content=_EX001_ROOT_CAUSE_NOTES),),
        ),
    ),
    fraction_time_used=0.66,
)

EX001_SILENT = Persona(
    persona_id="silent",
    exercise_slug="ex-001-invoice-drops-final-day",
    tier="Identical correct fix, one terse commit, NOTES.md untouched",
    rationale=(
        "The documentation probe, repeated on a different exercise type so a "
        "documentation miscalibration can be told apart from an ex-005 quirk. Same code "
        "as root-cause minus the added tests; the brief explicitly asks for a written "
        "answer to Finance, so completeness should drop here as well as documentation. "
        "Time is set above half the box so the critical-bug speed bonus does not "
        "confound the comparison."
    ),
    predicted_letter="C+",
    notes_md="",
    commits=(
        Commit(
            at_minute=14,
            message="fix period filter",
            edits=(
                Edit(
                    path="billing/services.py",
                    find=_EX001_BROKEN_FILTER,
                    replace=(
                        "    return LineItem.objects.filter(\n"
                        "        tenant_id=tenant_id,\n"
                        "        created_at__date__gte=period_start,\n"
                        "        created_at__date__lte=period_end,\n"
                        "    )"
                    ),
                ),
            ),
        ),
    ),
    fraction_time_used=0.57,
)

EX001_WIDENED_BOUND = Persona(
    persona_id="widened-bound",
    exercise_slug="ex-001-invoice-drops-final-day",
    tier="Symptom patch: widened the bound by a day, kept the type confusion",
    rationale=(
        "The symptom-patch probe the grading notes name explicitly: "
        "`period_end + timedelta(days=1)` passes every required check while leaving the "
        "date-versus-datetime confusion in the code, so the notes direct a grader to cap "
        "correctness around 70 and set symptom_patch_suspected. The only mechanical "
        "signal is stretch check S1 (`created_at__lt` still present), which is not a "
        "gate -- so if the rubric misses this, it is reading green checks as quality. "
        "The writeup is plausible and shallow rather than absent, which is the realistic "
        "version of this mistake."
    ),
    predicted_letter="C-",
    notes_md=_EX001_WIDENED_NOTES,
    commits=(
        Commit(
            at_minute=8,
            message=(
                "fix(billing): include the final day in the period\n"
                "\n"
                "The upper bound was exclusive so the last day was dropped. Adding a day\n"
                "to period_end covers it and fixes the single-day case too."
            ),
            edits=(
                Edit(
                    path="billing/services.py",
                    find="from datetime import date",
                    replace="from datetime import date, timedelta",
                ),
                Edit(
                    path="billing/services.py",
                    find=_EX001_BROKEN_FILTER,
                    replace=(
                        "    return LineItem.objects.filter(\n"
                        "        tenant_id=tenant_id,\n"
                        "        created_at__gte=period_start,\n"
                        "        created_at__lt=period_end + timedelta(days=1),\n"
                        "    )"
                    ),
                ),
            ),
        ),
        Commit(
            at_minute=12,
            message="docs: notes on the billing period fix",
            edits=(Edit(path="NOTES.md", content=_EX001_WIDENED_NOTES),),
        ),
    ),
    fraction_time_used=0.48,
)

EX001_PERSONAS = (EX001_ROOT_CAUSE, EX001_SILENT, EX001_WIDENED_BOUND)


# ---------------------------------------------------------------------------
# ex-002 -- the usage dashboard N+1
#
# `reporting/services.py::project_usage_summary` loops over projects and issues one
# `.aggregate()` per project, so query count grows linearly with the customer's size.
# ---------------------------------------------------------------------------

_EX002_BROKEN_LOOP = """\
    summaries = []
    for project in Project.objects.filter(tenant_id=tenant_id).order_by("name"):
        items = line_items_for_period(tenant_id, period_start, period_end).filter(
            project=project
        )
        totals = items.aggregate(count=Count("id"), total=Sum("amount_cents"))
        summaries.append(
            ProjectUsage(
                project_id=project.pk,
                project_name=project.name,
                line_item_count=totals["count"] or 0,
                total_cents=totals["total"] or 0,
            )
        )
    return summaries"""

_EX002_ANNOTATED = """\
    rows = (
        Project.objects.filter(tenant_id=tenant_id)
        .annotate(
            item_count=Count(
                "line_items", filter=models_q_for_period(period_start, period_end)
            ),
            item_total=Sum(
                "line_items__amount_cents",
                filter=models_q_for_period(period_start, period_end),
            ),
        )
        .order_by("name")
        .values("id", "name", "item_count", "item_total")
    )
    return [
        ProjectUsage(
            project_id=row["id"],
            project_name=row["name"],
            line_item_count=row["item_count"] or 0,
            total_cents=row["item_total"] or 0,
        )
        for row in rows
    ]"""

_EX002_PREFETCHED = """\
    prefetched = (
        Project.objects.filter(tenant_id=tenant_id)
        .order_by("name")
        .prefetch_related(
            Prefetch(
                "line_items",
                queryset=LineItem.objects.filter(
                    created_at__date__gte=period_start,
                    created_at__date__lte=period_end,
                ),
                to_attr="period_items",
            )
        )
    )
    return [
        ProjectUsage(
            project_id=project.pk,
            project_name=project.name,
            line_item_count=len(project.period_items),
            total_cents=sum(item.amount_cents for item in project.period_items),
        )
        for project in prefetched
    ]"""

_EX002_DOCSTRING_ANCHOR = '''    """Summarise each of a tenant's projects for a billing period.

    Args:'''

_EX002_DOCSTRING_RESTORED = '''    """Summarise each of a tenant's projects for a billing period.

    Aggregated in a single query with annotations. Looping over projects and
    issuing one aggregate per project would be an N+1: correct, but it turns one
    round trip into one-per-project, which is what makes this endpoint fall over on
    a tenant with hundreds of projects.

    Args:'''

_EX002_ROOT_CAUSE_NOTES = """\
# Engineering notes

## Diagnosis

Measured first. `python bench/bench_queries.py` on the seeded 40-project tenant:

    queries: 41

One query for the project list, then one per project. At Initech's 400 projects that is
401 round trips, which is why a 30-second timeout is reached for them and nobody else:
the cost is linear in project count, and 95% of tenants have fewer than ten.

After the change:

    queries: 1

`test_summary_query_count_is_flat_as_projects_grow` now passes because doubling the
projects from 12 to 24 leaves the count unchanged -- constant, not merely smaller.

## Root cause

`reporting/services.py::project_usage_summary` looped over
`Project.objects.filter(tenant_id=...)` and called `.aggregate()` inside the loop. Each
iteration is a separate round trip, so total cost is `1 + N`. Nothing was wrong with the
numbers; the shape of the access pattern was wrong.

The module already had the answer in it: `models_q_for_period` was defined and unused.
That helper exists precisely to be the `filter=` argument of an annotation, which is a
strong hint about the intended implementation.

## The fix

One annotated query:

    .annotate(
        item_count=Count("line_items", filter=models_q_for_period(...)),
        item_total=Sum("line_items__amount_cents", filter=models_q_for_period(...)),
    )

`Count`/`Sum` with a `filter=` argument compile to `FILTER (WHERE ...)` in Postgres, so
both aggregates are computed for every project in a single pass. `.values(...)` keeps
the projection narrow; ordering by name is unchanged.

This preserves the LEFT JOIN semantics, which is the part that is easy to lose: a
project with no usage in the period still appears, with `item_count` 0 and `item_total`
`None`, and the existing `or 0` coalesces it. `test_summary_includes_a_project_with_no_usage`
is the guard.

Restored the docstring paragraph explaining why this is aggregated rather than looped.

## Why this fix and not the alternatives

Rejected `prefetch_related` plus summing in Python. It flattens the query count, so it
passes R1-R3 and looks equivalent on the benchmark -- but it loads every line item for
every project into memory to add up numbers the database can add up without sending
them. For Initech that is trading 400 round trips for potentially millions of rows. The
benchmark counts queries, so it would not show the cost; that is a limit of the
benchmark, not evidence the approach is fine.

Rejected caching, which the brief forbids -- Finance reconciles against these numbers
and needs them live.

Rejected any change to the response shape; the dashboard is shipped against it.

## What I verified

- `python bench/bench_queries.py`: 41 -> 1 query for 40 projects.
- R1 and R2 pass, and the full suite is green including
  `test_summary_includes_a_project_with_no_usage` and the ordering assertions.
- Compared the totals for the seeded tenant before and after: identical, which is the
  thing a rewrite of an aggregate most needs to prove.
- Read the generated SQL with `.query` to confirm one statement with two FILTER clauses
  and a LEFT OUTER JOIN rather than an inner join.

## Risks and follow-ups

The two `models_q_for_period(...)` calls build the predicate twice. Harmless, but if a
third aggregate is added it should be hoisted to a local.

`Count("line_items", filter=...)` counts rows, matching the previous `Count("id")`. If a
line item is ever soft-deleted, both the old code and this would need the same extra
predicate -- the fix does not change that exposure.

## What I'd do with more time

1. Add a query-count guard to the perf suite for the *export* path too; it resolves
   projects and line items in a similar shape and nothing pins its cost.
2. Have the benchmark report rows fetched alongside queries. It would then be able to
   distinguish this fix from the prefetch approach, which currently looks identical to
   it.
3. Ask why the p95 alert never fired: an alert that averages over tenants of wildly
   different sizes cannot see this class of problem, and per-tenant p95 would have.
"""

_EX002_PREFETCH_NOTES = """\
# Engineering notes

## Diagnosis

`python bench/bench_queries.py` reported 41 queries for 40 projects, so the endpoint was
issuing one query per project on top of the project list. Initech has 400 projects,
hence the timeout.

## Root cause

`project_usage_summary` called `.aggregate()` inside a loop over the tenant's projects,
which is an N+1.

## The fix

Replaced the per-project aggregate with a single `prefetch_related` using a `Prefetch`
object scoped to the period, then summed the line items in Python. The benchmark now
reports 2 queries regardless of how many projects the tenant has, and the response shape
is unchanged.

## Why this fix and not the alternatives

Prefetching is the standard Django answer to an N+1 and it keeps the period filter in
one obvious place instead of spreading it across annotation `filter=` arguments, which
I find harder to read. The query count is flat, which is what the brief asked for.

## What I verified

- `python bench/bench_queries.py`: 2 queries, down from 41.
- The query count is identical for 12 and 24 projects.
- Full suite green, including the project-with-no-usage case and the ordering.

## Risks and follow-ups

None that I can see -- the queries are constant and the numbers match.

## What I'd do with more time

Add the same prefetch treatment to the export path.
"""

EX002_ROOT_CAUSE = Persona(
    persona_id="root-cause",
    exercise_slug="ex-002-project-summary-n-plus-one",
    tier="Single annotated query, measured before and after, reasoned about rows not just queries",
    rationale=(
        "The upper anchor, and it also tests whether the rubric rewards *measuring*. The "
        "grading notes call quoting before-and-after query counts the strongest signal, "
        "and this writeup does that, notices the unused models_q_for_period helper, and "
        "explains why the prefetch alternative is worse in a way the benchmark cannot "
        "see. It should outrank the prefetch persona clearly despite identical check "
        "results."
    ),
    predicted_letter="A",
    notes_md=_EX002_ROOT_CAUSE_NOTES,
    commits=(
        Commit(
            at_minute=9,
            message=(
                "perf(reporting): aggregate project usage in one query\n"
                "\n"
                "project_usage_summary looped over the tenant's projects and issued one\n"
                ".aggregate() per project, so cost was 1 + N round trips. The benchmark\n"
                "reported 41 queries for 40 projects; Initech has 400, which is why the\n"
                "dashboard times out for them and for nobody else.\n"
                "\n"
                "Replaced with a single annotated query using Count/Sum with filter=,\n"
                "via the models_q_for_period helper that was already in the module and\n"
                "unused. Postgres computes both aggregates per project in one pass as\n"
                "FILTER (WHERE ...) clauses.\n"
                "\n"
                "Benchmark: 41 queries -> 1, and flat as project count grows.\n"
                "\n"
                "The LEFT JOIN semantics are preserved on purpose so a project with no\n"
                "usage still appears with zeroes, which an inner join would drop.\n"
                "\n"
                "Refs INC-2410"
            ),
            edits=(
                Edit(
                    path="reporting/services.py",
                    find=_EX002_BROKEN_LOOP,
                    replace=_EX002_ANNOTATED,
                ),
                Edit(
                    path="reporting/services.py",
                    find=_EX002_DOCSTRING_ANCHOR,
                    replace=_EX002_DOCSTRING_RESTORED,
                ),
            ),
        ),
        Commit(
            at_minute=17,
            message=(
                "docs: write up the N+1, the measurements, and the rejected prefetch\n"
                "\n"
                "Records 41 -> 1 queries, why the cost was linear in project count, and\n"
                "why prefetch-and-sum-in-Python was rejected: it flattens the query\n"
                "count the benchmark measures while still loading every row."
            ),
            edits=(Edit(path="NOTES.md", content=_EX002_ROOT_CAUSE_NOTES),),
        ),
    ),
    fraction_time_used=0.63,
)

EX002_SILENT = Persona(
    persona_id="silent",
    exercise_slug="ex-002-project-summary-n-plus-one",
    tier="Identical correct fix, one terse commit, NOTES.md untouched",
    rationale=(
        "The documentation probe on the latency exercise. Note the brief asks for an "
        "explanation of why the original cost grew with project count, so this persona "
        "misses a definition-of-done item as well as the writeup -- the interesting "
        "question is whether the rubric double-counts that as both a documentation and a "
        "completeness miss, and whether the result is still credible next to the "
        "green-but-worse prefetch persona."
    ),
    predicted_letter="C+",
    notes_md="",
    commits=(
        Commit(
            at_minute=16,
            message="fix n+1 in project_usage_summary",
            edits=(
                Edit(
                    path="reporting/services.py",
                    find=_EX002_BROKEN_LOOP,
                    replace=_EX002_ANNOTATED,
                ),
            ),
        ),
    ),
    fraction_time_used=0.52,
)

EX002_PREFETCH = Persona(
    persona_id="prefetch-python",
    exercise_slug="ex-002-project-summary-n-plus-one",
    tier="Prefetch plus Python summation: flat query count, every row loaded",
    rationale=(
        "The defensible-but-worse tier, and the hardest judgment in the corpus. Every "
        "required check passes with a constant 2 queries, the benchmark cannot see the "
        "difference, and the approach is a textbook Django answer -- so nothing "
        "mechanical distinguishes it from root-cause. The grading notes say to accept it "
        "as correct but mark engineering down and say why. It should land clearly below "
        "root-cause and clearly above a symptom patch; a rubric that cannot produce that "
        "middle verdict is only sorting into pass and fail."
    ),
    predicted_letter="B-",
    notes_md=_EX002_PREFETCH_NOTES,
    commits=(
        Commit(
            at_minute=11,
            message=(
                "perf(reporting): prefetch line items instead of aggregating per project\n"
                "\n"
                "The summary issued one aggregate query per project (41 for 40 projects).\n"
                "Replaced with a single scoped Prefetch and summed in Python, so the\n"
                "query count is 2 and does not grow with the number of projects."
            ),
            edits=(
                Edit(
                    path="reporting/services.py",
                    find="from django.db.models import Count, Sum",
                    replace="from django.db.models import Count, Prefetch, Sum",
                ),
                Edit(
                    path="reporting/services.py",
                    find=_EX002_BROKEN_LOOP,
                    replace=_EX002_PREFETCHED,
                ),
            ),
        ),
        Commit(
            at_minute=18,
            message="docs: notes on the reporting N+1 fix",
            edits=(Edit(path="NOTES.md", content=_EX002_PREFETCH_NOTES),),
        ),
    ),
    fraction_time_used=0.60,
)

EX002_PERSONAS = (EX002_ROOT_CAUSE, EX002_SILENT, EX002_PREFETCH)


# ---------------------------------------------------------------------------
# ex-003 -- the export leaks across tenants
#
# `reporting/exports.py::resolve_project` looks a project up by slug with no tenant
# predicate. Slugs are unique per tenant, so the query can return another customer's
# project and the export then faithfully dumps their line items.
# ---------------------------------------------------------------------------

_EX003_BROKEN_LOOKUP = """\
    project = Project.objects.filter(slug=slug).first()
    if project is None:
        logger.info("project %r not found", slug)
        raise ProjectNotFound(slug)
    return project"""

_EX003_SCOPED_LOOKUP = """\
    project = Project.objects.for_tenant(tenant_id).filter(slug=slug).first()
    if project is None:
        logger.info("project %r not found for tenant %s", slug, tenant_id)
        raise ProjectNotFound(slug)
    return project"""

_EX003_DOCSTRING_ANCHOR = '''    """Look up one of a tenant's projects by slug.

    Args:'''

_EX003_DOCSTRING_RESTORED = '''    """Look up one of a tenant's projects by slug.

    Scoped to the tenant in SQL, through the TenantScopedQuerySet rather than an
    ad-hoc filter, so the scoping is the default rather than something each call
    site has to remember. Slugs are only unique within a tenant, so an unscoped
    lookup hands back another customer's project -- and everything downstream then
    faithfully exports their data.

    Args:'''

_EX003_RAISES_ANCHOR = """\
        ProjectNotFound: If no project has that slug."""

_EX003_RAISES_RESTORED = """\
        ProjectNotFound: If this tenant has no project with that slug. Deliberately
            indistinguishable from "exists but belongs to someone else", so the
            response cannot be used to enumerate other tenants' projects."""

_EX003_ROOT_CAUSE_NOTES = """\
# Engineering notes

## What was exposed, and to whom

**One project's full line-item export, cross-tenant, via `GET /exports/<slug>`.** Each
exported row carries `created_at`, `kind`, `description` and `amount_cents`, so the
exposure includes usage volumes, spend, and free-text descriptions -- which in our data
frequently name internal systems.

The leak is **asymmetric, and that matters for scoping the incident.** `Project` has
`ordering = ["name"]`, and with no tenant predicate the query returns the first row
matching the slug. So for a slug held by two tenants, whichever project sorts first by
name wins, for *every* requester. Acme asking for `website` tends to get Acme's, while
Globex asking for `website` also gets Acme's. That is why it survived review and did
not reproduce for whoever tested it: the person testing was usually the tenant who
happened to win.

Exposure is therefore limited to **slugs that collide across tenants**, and the losing
tenant in each collision is the one who saw someone else's data. A list of collisions
is one query:

    SELECT slug FROM projects_project GROUP BY slug HAVING COUNT(DISTINCT tenant_id) > 1;

Legal will want that list joined against the access log for `/exports/`; I have not run
it against production, and it should be run before anyone estimates blast radius from
this note alone.

## Root cause

`reporting/exports.py::resolve_project` ran `Project.objects.filter(slug=slug).first()`
with no tenant predicate. Slugs are unique **per tenant** -- that is the shipped
constraint, `unique_project_slug_per_tenant` -- not globally, so a slug is not an
identifier on its own. Everything downstream is correct given the project it is handed;
the trust boundary was crossed at this one lookup.

## The fix

Routed the lookup through the scoped queryset that already exists:

    Project.objects.for_tenant(tenant_id).filter(slug=slug)

rather than adding `tenant_id=tenant_id` to the existing `filter()`. Both close this
instance; only the first makes the scoping idiomatic, so the next person who adds a
lookup-by-natural-key in this module has an obvious thing to copy. `TenantScopedQuerySet`
is already the manager on `Project` and was simply not being used here.

The predicate is applied **in SQL**, so another tenant's row is never read off disk.
That is the distinction `ARCHITECTURE.md` draws and it is the one that matters: a Python
check after the fact is a different guarantee, discussed below.

The `ProjectNotFound` path is unchanged and still raises the same exception with the
same message whether the slug does not exist or belongs to someone else. That is
deliberate -- distinguishing the two turns the endpoint into an enumeration oracle for
other tenants' project names -- and I restored the docstring that said so.

## Why this fix and not the alternatives

Rejected resolving unscoped and then checking `project.tenant_id == tenant_id` in
Python. It passes the same tests, and it is not a fix in the sense that matters: the row
has already crossed the trust boundary. It leaves the leak one early-return, one logging
statement, or one `except` away from returning, and it still exposes existence through
timing and through anything that logs the resolved object.

Rejected raising a distinguishable error for "belongs to another tenant" -- an
enumeration oracle.

Rejected making slugs globally unique. It contradicts the shipped constraint and would
break every customer who reuses a common slug.

## What I verified

- The three named tests pass: `test_resolve_never_returns_another_tenants_project`,
  `test_resolve_raises_for_a_slug_owned_by_someone_else`, and
  `test_export_for_each_tenant_is_disjoint`.
- Full suite green; `bash ci/run_ci.sh` exits 0 including the separate security job.
- Checked the generated SQL includes `tenant_id = %s`, rather than relying on the test
  passing for some other reason.

## Whether anything else has the same weakness

I grepped `reporting/`, `billing/`, `projects/` and `api/` for `objects.filter(` and
`objects.get(` and read each hit for a missing tenant predicate:

- `reporting/exports.py` -- this one. Fixed.
- `billing.services.line_items_for_period` -- takes `tenant_id` and filters on it.
- `reporting.services.project_usage_summary` -- filters `tenant_id`.
- The API layer resolves the tenant from the API key in middleware and passes the id
  down, so the ids themselves are trustworthy.

I found no second instance. I would not call that a clean bill of health: the audit was
a grep under time pressure, it covers resolution by natural key rather than every query,
and it does not cover the admin or any management command.

## Risks and follow-ups

The fix is one line of behaviour and cannot break a tenant who was getting the right
project. The tenants who were *receiving* someone else's project will now get a 404
where they previously got data -- correct, and worth telling support before the tickets
arrive.

## What I'd do with more time

1. **Make this class of bug unreachable rather than fixed.** A check that fails the
   build when a tenant-owned model is queried through `objects.filter()` without a
   tenant predicate in a request path -- either a lint rule over the AST, or a test
   that walks the request-serving modules. The one-line fix does nothing to stop the
   next one.
2. Add the cross-tenant slug-collision query above as a monitoring check, so we know
   where the risk is concentrated rather than discovering it per incident.
3. Consider making `for_current_tenant()` the only public way to reach these querysets
   in request paths, so an unscoped query has to be written deliberately.
"""

_EX003_PYTHON_FILTER_NOTES = """\
# Engineering notes

## What was exposed

A tenant could download another tenant's project export if they both used the same
project slug. The export contains line items with descriptions and amounts.

## Root cause

`resolve_project` looked the project up by slug only. Slugs are unique per tenant, not
globally, so the query could return a project belonging to someone else.

## The fix

Kept the existing lookup and picked the right project out of the results: fetch the
projects matching the slug, then select the one belonging to the requesting tenant. If
none of them does, raise `ProjectNotFound`, exactly as if the slug did not exist. The
caller cannot tell the two cases apart, so there is no way to enumerate other tenants'
projects.

I had to fetch all the matches rather than just the first one, because with the default
ordering by name the first row is not necessarily the requester's -- that is what made
the original bug asymmetric.

## Why this fix and not the alternatives

Doing the ownership check in Python keeps the rule visible right next to the error
handling instead of being buried in a queryset method, and it reads as an explicit
statement of intent. The observable behaviour is the same as scoping the query -- the
caller gets their own project or `ProjectNotFound` -- so I went with the version that is
clearer to the next reader.

## What I verified

All three export tests pass, the full suite is green, and `bash ci/run_ci.sh` exits 0
including the security job.

## Whether anything else is affected

I looked at the other lookups in `reporting/` and they all take a `tenant_id`, so I
believe this was the only one.

## Risks and follow-ups

Low. Tenants who were previously receiving another tenant's export will now get a 404.

## What I'd do with more time

Add a test for the case where two tenants use the same slug and both request it.
"""

EX003_ROOT_CAUSE = Persona(
    persona_id="root-cause",
    exercise_slug="ex-003-export-leaks-across-tenants",
    tier="Scoped in SQL via the existing queryset, with a real incident writeup and an audit",
    rationale=(
        "The upper anchor on the hardest exercise. Uses for_tenant() rather than an "
        "ad-hoc filter (the grading notes say to strongly prefer it), explains the "
        "asymmetry of the leak, and does what the brief demands of a SEV-1 writeup that "
        "legal will read: what was exposed, to whom, and whether anything else shares "
        "the weakness -- including an honest statement of the audit's limits."
    ),
    predicted_letter="A",
    notes_md=_EX003_ROOT_CAUSE_NOTES,
    commits=(
        Commit(
            at_minute=9,
            message=(
                "fix(exports): scope project resolution to the requesting tenant\n"
                "\n"
                "resolve_project looked a project up by slug with no tenant predicate.\n"
                "Slugs are unique per tenant (unique_project_slug_per_tenant), not\n"
                "globally, so the query returned whichever row sorted first by name --\n"
                "for every requester, not just the owner. Everything downstream then\n"
                "exported that project's line items faithfully.\n"
                "\n"
                "Routed through Project.objects.for_tenant(), the TenantScopedQuerySet\n"
                "already installed as the model's manager, rather than adding\n"
                "tenant_id= to the existing filter. Both close this instance; this one\n"
                "leaves the idiom in place for the next lookup by natural key.\n"
                "\n"
                "The predicate is applied in SQL, so another tenant's row is never read\n"
                "off disk -- a Python check after the query would not be the same\n"
                "guarantee.\n"
                "\n"
                "ProjectNotFound is still raised identically whether the slug is absent\n"
                "or owned by someone else, so the endpoint cannot be used to enumerate\n"
                "other tenants' project names."
            ),
            edits=(
                Edit(
                    path="reporting/exports.py",
                    find=_EX003_BROKEN_LOOKUP,
                    replace=_EX003_SCOPED_LOOKUP,
                ),
                Edit(
                    path="reporting/exports.py",
                    find=_EX003_DOCSTRING_ANCHOR,
                    replace=_EX003_DOCSTRING_RESTORED,
                ),
                Edit(
                    path="reporting/exports.py",
                    find=_EX003_RAISES_ANCHOR,
                    replace=_EX003_RAISES_RESTORED,
                ),
            ),
        ),
        Commit(
            at_minute=22,
            message=(
                "docs: incident writeup for the cross-tenant export leak\n"
                "\n"
                "What was exposed (line items with descriptions and amounts), to whom\n"
                "(the losing side of every cross-tenant slug collision, which is why it\n"
                "never reproduced for the reviewer), and the audit of other lookups by\n"
                "natural key, including what that audit does not cover."
            ),
            edits=(Edit(path="NOTES.md", content=_EX003_ROOT_CAUSE_NOTES),),
        ),
    ),
    fraction_time_used=0.70,
)

EX003_SILENT = Persona(
    persona_id="silent",
    exercise_slug="ex-003-export-leaks-across-tenants",
    tier="Correct SQL scoping, one terse commit, NOTES.md untouched",
    rationale=(
        "The documentation probe where the writeup is most obviously part of the job: "
        "this is a SEV-1 whose brief says legal will read NOTES.md. A silent fix here "
        "should be punished harder than a silent fix on ex-005, and if the rubric gives "
        "it the same letter it is applying the documentation weight mechanically rather "
        "than reading the brief."
    ),
    predicted_letter="C",
    notes_md="",
    commits=(
        Commit(
            at_minute=12,
            message="scope project lookup by tenant",
            edits=(
                Edit(
                    path="reporting/exports.py",
                    find=_EX003_BROKEN_LOOKUP,
                    replace=(
                        "    project = Project.objects.filter("
                        "tenant_id=tenant_id, slug=slug).first()\n"
                        "    if project is None:\n"
                        '        logger.info("project %r not found", slug)\n'
                        "        raise ProjectNotFound(slug)\n"
                        "    return project"
                    ),
                ),
            ),
        ),
    ),
    fraction_time_used=0.45,
)

EX003_PYTHON_FILTER = Persona(
    persona_id="python-filter",
    exercise_slug="ex-003-export-leaks-across-tenants",
    tier="Resolves unscoped, then checks ownership in Python",
    rationale=(
        "The green-but-wrong probe for the security exercise, and the sharpest one in "
        "the corpus. Every required check passes -- the row is never returned and the "
        "error is indistinguishable, so even the enumeration test is satisfied -- yet "
        "the grading notes call this disqualifying, because the row has already crossed "
        "the trust boundary and the fix is one early return away from leaking again. "
        "The TENANT_ISOLATION type guidance says exactly this. The writeup argues for "
        "the approach on readability grounds, which is how the mistake is actually made. "
        "If this scores near the silent-but-correct persona, the rubric is treating "
        "security fixes as ordinary correctness."
    ),
    predicted_letter="D",
    notes_md=_EX003_PYTHON_FILTER_NOTES,
    commits=(
        Commit(
            at_minute=10,
            message=(
                "fix(exports): pick the requesting tenant's project out of the matches\n"
                "\n"
                "Slugs are only unique per tenant, so the lookup could return someone\n"
                "else's project. Now selects the match belonging to the caller and\n"
                "raises ProjectNotFound otherwise, so they cannot tell the difference\n"
                "between a missing slug and one they do not own.\n"
                "\n"
                "Fetches all matches rather than the first, since the default ordering\n"
                "by name means the first row is not necessarily the requester's."
            ),
            edits=(
                Edit(
                    path="reporting/exports.py",
                    find=_EX003_BROKEN_LOOKUP,
                    replace=(
                        "    candidates = list(Project.objects.filter(slug=slug))\n"
                        "    project = next(\n"
                        "        (match for match in candidates if match.tenant_id == tenant_id),\n"
                        "        None,\n"
                        "    )\n"
                        "    if project is None:\n"
                        '        logger.info("project %r not found", slug)\n'
                        "        raise ProjectNotFound(slug)\n"
                        "    return project"
                    ),
                ),
            ),
        ),
        Commit(
            at_minute=16,
            message="docs: notes on the export isolation fix",
            edits=(Edit(path="NOTES.md", content=_EX003_PYTHON_FILTER_NOTES),),
        ),
    ),
    fraction_time_used=0.55,
)

EX003_PERSONAS = (EX003_ROOT_CAUSE, EX003_SILENT, EX003_PYTHON_FILTER)


# ---------------------------------------------------------------------------
# ex-004 -- implement the Wilson interval
#
# Build-shaped rather than fix-shaped: `wilson_interval` raises NotImplementedError and
# the tests fully specify the behaviour. The interesting detail is that at
# `successes == trials` the algebra cancels to exactly 1.0 but floating point lands on
# 0.9999999999999999, which `min(1.0, x)` will not clamp.
# ---------------------------------------------------------------------------

_EX004_STUB = '    raise NotImplementedError("wilson_interval is not implemented yet")'

_EX004_CORRECT = """\
    if trials == 0:
        return Interval(0.0, 0.0)
    if successes < 0 or successes > trials:
        raise ValueError(f"successes must be within 0..{trials}, got {successes}")

    proportion = successes / trials
    denominator = 1 + z**2 / trials
    centre = proportion + z**2 / (2 * trials)
    spread = z * math.sqrt(proportion * (1 - proportion) / trials + z**2 / (4 * trials**2))

    # Rounded before clamping. At p=1 the algebra cancels to exactly 1.0, but in
    # floating point it lands on 0.9999999999999999, which min() will not clamp --
    # so an "all successes" cohort would report an upper bound just under certainty.
    # Twelve places is far more precision than a proportion needs and makes the
    # boundary exact.
    lower = round((centre - spread) / denominator, 12)
    upper = round((centre + spread) / denominator, 12)
    return Interval(lower=max(0.0, lower), upper=min(1.0, upper))"""

_EX004_NAIVE_CLAMP = """\
    if trials == 0:
        return Interval(0.0, 0.0)
    if successes < 0 or successes > trials:
        raise ValueError(f"successes must be within 0..{trials}, got {successes}")

    proportion = successes / trials
    denominator = 1 + z**2 / trials
    centre = proportion + z**2 / (2 * trials)
    spread = z * math.sqrt(proportion * (1 - proportion) / trials + z**2 / (4 * trials**2))

    lower = (centre - spread) / denominator
    upper = (centre + spread) / denominator
    return Interval(lower=max(0.0, lower), upper=min(1.0, upper))"""

_EX004_ROOT_CAUSE_NOTES = """\
# Engineering notes

## What was asked

`wilson_interval` was stubbed with `NotImplementedError`; `tests/test_analytics.py`
specifies the behaviour completely, including the arithmetic in the docstrings. Six
tests were failing.

## Why Wilson rather than the normal approximation

The normal approximation is `p ± z·sqrt(p(1-p)/n)`. It fails exactly where Finance
lives:

* **Near 0 or 1 it produces bounds outside [0, 1].** At 6 of 6 conversions it gives an
  upper bound above 1, which the dashboard cannot render. Wilson's denominator
  `1 + z²/n` keeps the result inside the unit interval by construction.
* **At p = 0 or p = 1 its width collapses to zero.** Zero conversions out of 6 reads as
  "0%, certainly", which is the precise failure that started this: 2/6 against 3/6 was
  reported as a 30% drop. Wilson still returns a wide interval there, because six
  observations genuinely do not tell you much.
* **It is symmetric around p**, which a proportion near a boundary is not. Wilson's
  centre shifts to `p + z²/2n`, pulling the estimate toward 0.5 in proportion to how
  little data there is.

In short, the normal approximation is a good approximation for large n away from the
boundaries, and Finance's cohorts are neither.

## The implementation

Standard Wilson score interval, `math` only -- no new dependency, and `Z_95` was
already in the module:

    denominator = 1 + z²/n
    centre      = p + z²/(2n)
    spread      = z·sqrt(p(1-p)/n + z²/(4n²))
    bounds      = (centre ∓ spread) / denominator

`trials == 0` short-circuits to `Interval(0.0, 0.0)` before any division, so a new
cohort cannot raise `ZeroDivisionError` into the dashboard. Impossible counts raise
`ValueError`.

## The one thing that is not obvious

`test_wilson_stays_inside_zero_and_one_at_the_extremes` failed at first, with the
upper bound at `0.9999999999999999` instead of `1.0`.

This is **floating point, not the formula.** At `successes == trials`, `p = 1`, so
`p(1-p)/n` vanishes and the expression cancels algebraically to exactly 1. In binary
the intermediate terms do not cancel exactly, and the result lands one ulp below 1.
`min(1.0, x)` then leaves it alone -- the clamp cannot help, because the value is
already inside the range. The dashboard would have displayed "99.99999999999999%" for a
cohort that converted unanimously.

The fix is to `round(..., 12)` before clamping. Twelve decimal places is far more
precision than a proportion carries, and it makes the boundary exact. I would rather
round than special-case `successes == trials`, because the same one-ulp problem exists
just inside the boundary, where a special case would not fire.

I left a comment saying this, because the `round()` looks arbitrary otherwise and the
next person will delete it.

## What I verified

- All six `wilson_interval` tests pass, including the hand-derived numeric values.
- Full suite green; `bash ci/run_ci.sh` exits 0.
- Checked monotonicity by hand beyond what the tests assert: at a fixed proportion the
  width shrinks as n grows (0.5 at n=10 is roughly 0.56 wide, at n=1000 roughly 0.06).
- Confirmed no new imports: `math` was already there.

## Risks and follow-ups

`z` is a parameter with a 95% default, so a caller can ask for another level, but
`Z_95` is the only constant defined. If Finance asks for 99% intervals, someone will
paste a magic number in at the call site; a small mapping of level to z would pre-empt
that.

The interval is for a single proportion. If Finance starts comparing two cohorts --
which is what "conversion dropped" really means -- overlapping intervals are not the
right test, and I would expect that request next.

## What I'd do with more time

1. A property test: for random `0 <= k <= n`, assert `0 <= lower <= p <= upper <= 1`
   and that width decreases in n. That covers the boundary class of bug rather than the
   two boundary points the current tests name.
2. Plot the interval against the normal approximation for n from 5 to 500 and attach it
   to the Finance ticket -- it makes the case for Wilson faster than this note does.
"""

_EX004_NAIVE_CLAMP_NOTES = """\
# Engineering notes

## What was asked

Implement `wilson_interval`, which was stubbed with `NotImplementedError`.

## Why Wilson rather than the normal approximation

The normal approximation produces bounds outside [0, 1] when the proportion is near 0
or 1, and Finance's cohorts are small and often at the extremes -- a bound above 1
cannot be rendered on the dashboard. It also reports zero width at p = 0 or p = 1,
which makes a 6-person cohort look certain when it is not. Wilson keeps the interval
inside [0, 1] and stays wide at small n, which is the behaviour that was asked for.

## The implementation

The standard Wilson formula, using only `math` and the `Z_95` constant already in the
module:

    denominator = 1 + z²/n
    centre      = p + z²/(2n)
    spread      = z·sqrt(p(1-p)/n + z²/(4n²))
    bounds      = (centre ∓ spread) / denominator

Zero trials returns `Interval(0.0, 0.0)` before dividing. Negative successes, or more
successes than trials, raise `ValueError`.

## What I verified

Five of the six `wilson_interval` tests pass, including all the hand-derived numeric
values, the zero-trials case and both `ValueError` cases. The rest of the suite is
green and I added no dependencies.

## What is still failing, and what I think it is

`test_wilson_stays_inside_zero_and_one_at_the_extremes` fails at `successes == trials`.
I get an upper bound of `0.9999999999999999` where the test wants `1.0`.

I do not think the formula is wrong -- every other numeric case matches the expected
values exactly, and at p = 1 the algebra should cancel to exactly 1. My working theory
is that this is floating-point representation rather than arithmetic: the terms cancel
in exact arithmetic but not in binary, so the result lands just below 1 and
`min(1.0, upper)` has nothing to clamp because the value is already inside the range.

I ran out of time to confirm that and fix it properly. I did **not** want to guess at
a fix I could not justify -- special-casing `successes == trials` to return 1.0 would
make the test pass while hiding whatever the real cause is, and if my theory is wrong
that special case would be actively misleading.

## What I'd do with more time, in order

1. Print the unrounded upper bound at `successes == trials` to confirm it is one ulp
   below 1 rather than genuinely different. Ten minutes.
2. If it is representation, round to about twelve decimal places before clamping rather
   than special-casing the endpoint -- the same one-ulp problem exists just inside the
   boundary, where a special case would not fire.
3. Add a property test over random `0 <= k <= n` asserting the bounds stay in [0, 1],
   so this class of failure is caught at the boundary rather than at two specific
   points.

Do not ship this as it stands: at a 100% cohort the dashboard would render
"99.99999999999999%".
"""

EX004_ROOT_CAUSE = Persona(
    persona_id="root-cause",
    exercise_slug="ex-004-implement-revenue-analytics",
    tier="Complete implementation, float boundary diagnosed and explained",
    rationale=(
        "The upper anchor on the build-shaped exercise. Hits the stretch goal the "
        "grading notes describe -- diagnosing the 0.9999999999999999 upper bound as "
        "float representation rather than a formula error and saying so -- and answers "
        "the brief's actual question about why Wilson rather than the normal "
        "approximation in terms of behaviour, not formulae."
    ),
    predicted_letter="A",
    notes_md=_EX004_ROOT_CAUSE_NOTES,
    commits=(
        Commit(
            at_minute=14,
            message=(
                "feat(analytics): implement the Wilson score interval\n"
                "\n"
                "Standard Wilson bounds, math only -- Z_95 was already in the module and\n"
                "the brief forbids new numerical dependencies. Zero trials short-circuits\n"
                "to Interval(0.0, 0.0) before any division so a new cohort cannot break\n"
                "the dashboard; impossible counts raise ValueError."
            ),
            edits=(
                Edit(
                    path="reporting/analytics.py",
                    find=_EX004_STUB,
                    replace=_EX004_NAIVE_CLAMP,
                ),
            ),
        ),
        Commit(
            at_minute=23,
            message=(
                "fix(analytics): round before clamping so a 100% cohort reports 1.0\n"
                "\n"
                "At successes == trials the algebra cancels to exactly 1, but in binary\n"
                "the intermediate terms do not, and the result lands one ulp below 1.\n"
                "min(1.0, x) cannot help: the value is already inside the range. An\n"
                "all-converting cohort would have rendered as 99.99999999999999%.\n"
                "\n"
                "Rounding to 12 places before clamping makes the boundary exact.\n"
                "Preferred over special-casing successes == trials, because the same\n"
                "one-ulp problem exists just inside the boundary where a special case\n"
                "would not fire.\n"
                "\n"
                "Comment retained deliberately -- the round() reads as arbitrary\n"
                "otherwise and would be deleted by the next person through."
            ),
            edits=(
                Edit(
                    path="reporting/analytics.py",
                    find=_EX004_NAIVE_CLAMP,
                    replace=_EX004_CORRECT,
                ),
            ),
        ),
        Commit(
            at_minute=29,
            message=(
                "docs: why Wilson over the normal approximation, and the float boundary\n"
                "\n"
                "Answers the brief's question in terms of behaviour at small n and near\n"
                "the boundaries rather than by restating the formula, and records the\n"
                "one-ulp diagnosis so the round() is not mistaken for superstition."
            ),
            edits=(Edit(path="NOTES.md", content=_EX004_ROOT_CAUSE_NOTES),),
        ),
    ),
    fraction_time_used=0.75,
)

EX004_SILENT = Persona(
    persona_id="silent",
    exercise_slug="ex-004-implement-revenue-analytics",
    tier="Identical complete implementation, one terse commit, NOTES.md untouched",
    rationale=(
        "The documentation probe on build-shaped work, where the code is arguably more "
        "self-evident than a bug fix and the writeup correspondingly less load-bearing "
        "-- except the brief asks a direct question (why Wilson) that only the writeup "
        "can answer. Comparing this persona's gap from root-cause against the same gap "
        "on ex-005 and ex-003 shows whether the documentation weight is applied "
        "uniformly regardless of what the brief asked for."
    ),
    predicted_letter="C+",
    notes_md="",
    commits=(
        Commit(
            at_minute=21,
            message="implement wilson_interval",
            edits=(
                Edit(
                    path="reporting/analytics.py",
                    find=_EX004_STUB,
                    replace=_EX004_CORRECT,
                ),
            ),
        ),
    ),
    fraction_time_used=0.58,
)

EX004_HONEST_PARTIAL = Persona(
    persona_id="honest-partial",
    exercise_slug="ex-004-implement-revenue-analytics",
    tier="Formula right, float boundary unfixed, diagnosed honestly and flagged do-not-ship",
    rationale=(
        "The opposite probe to the green-but-wrong personas: work that FAILS a required "
        "check but is exactly the behaviour the rubric claims to reward. R1 fails on the "
        "extremes test, so the unsolved gate caps this at C+ no matter how good the "
        "writeup is. The system prompt says not to penalise a well-diagnosed partial fix "
        "for being partial; the gate says otherwise. The cap makes C+ the mechanical "
        "answer, so the thing to watch is whether the score lands just under the cap "
        "(the rubric recognising the quality) or far below it (the rubric punishing the "
        "failure twice -- once by cap, once by score)."
    ),
    predicted_letter="C+",
    notes_md=_EX004_NAIVE_CLAMP_NOTES,
    commits=(
        Commit(
            at_minute=15,
            message=(
                "feat(analytics): implement the Wilson score interval\n"
                "\n"
                "Standard Wilson bounds using math and the existing Z_95 constant; no\n"
                "new dependencies. Zero trials returns Interval(0.0, 0.0); impossible\n"
                "counts raise ValueError."
            ),
            edits=(
                Edit(
                    path="reporting/analytics.py",
                    find=_EX004_STUB,
                    replace=_EX004_NAIVE_CLAMP,
                ),
            ),
        ),
        Commit(
            at_minute=33,
            message=(
                "docs: record the failing extremes case and the one-ulp hypothesis\n"
                "\n"
                "test_wilson_stays_inside_zero_and_one_at_the_extremes still fails at\n"
                "successes == trials: upper comes out 0.9999999999999999. Every other\n"
                "numeric case matches exactly, so I believe this is float\n"
                "representation rather than the formula, but I could not confirm it in\n"
                "the time available.\n"
                "\n"
                "Deliberately not special-casing successes == trials to force the test\n"
                "green -- that would hide the cause if my theory is wrong. Flagged\n"
                "do-not-ship in NOTES.md."
            ),
            edits=(Edit(path="NOTES.md", content=_EX004_NAIVE_CLAMP_NOTES),),
        ),
    ),
    fraction_time_used=0.95,
)

EX004_PERSONAS = (EX004_ROOT_CAUSE, EX004_SILENT, EX004_HONEST_PARTIAL)
