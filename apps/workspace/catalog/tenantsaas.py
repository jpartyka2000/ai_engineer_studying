"""Exercises built on the ``tenantsaas`` base application.

Each entry is a ``(base_app, mutations)`` pair rather than its own codebase, which is
what makes a catalog of fifty authorable.

Baselines live in ``baselines.json`` because they are **measured**, not authored:
the verification harness applies each mutation, records exactly which tests fail,
and asserts exact set equality on every later run. A hand-written baseline would
make that check meaningless, and a superset of failures would mean the injected
defect broke more than intended.
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
        KeyError: If no baseline has been measured, which should fail the seed
            command rather than silently ship an ungradeable exercise.
    """
    data = _BASELINES[slug]
    return {
        "failing_nodes": data["failing_nodes"],
        "passing_nodes": data["passing_nodes"],
        "metrics": data.get("metrics", {}),
    }


#: Protected in most exercises: the tests are the proof, so editing them is tampering.
STANDARD_PROTECTED = ["tests/**", "pytest.ini"]

#: Shared context: the two places the inclusive-period and tenant-scope rules are
#: written down, which is what a reviewer needs to judge whether a fix fits.
ARCHITECTURE_EXCERPT = {
    "path": "ARCHITECTURE.md",
    "line_range": "20-50",
    "why": "States the tenant-boundary rules, including that scoping must happen in SQL.",
}


# ---------------------------------------------------------------------------
# ex-001 -- fix a critical bug fast
# ---------------------------------------------------------------------------

EX001 = {
    "slug": "ex-001-invoice-drops-final-day",
    "exercise_number": 1,
    "title": "SEV-2: March invoices are short by a day's usage",
    "exercise_type": ExerciseType.CRITICAL_BUG,
    "base_app": BaseApp.TENANTSAAS,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "date_boundary_off_by_one",
    "time_limit_minutes": 30,
    "expected_time_minutes": 19,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["django", "postgres", "billing", "timezones", "orm"],
    "brief_md": """\
## INC-2291 — customers are being under-billed

**Severity:** SEV-2
**Reported by:** Finance, via #billing-oncall

Finance reconciled March invoices against the metering data this morning and found
that **every invoice is missing the last day of the period**. Across all tenants that
is roughly $40k of usage that was never billed.

One customer noticed the other direction too: they queried
`/usage?period_start=2026-03-10&period_end=2026-03-10` for a single day and got zero,
even though they know they had usage that day.

### Reproducing it

```bash
docker compose up -d --wait
make migrate
make test
```

`tests/test_billing.py::test_period_includes_items_on_the_final_day` is the most
direct expression of the problem.

### What we know

- Billing periods are **inclusive at both ends**. An invoice for 1–31 March covers
  usage recorded right up to `23:59:59` on the 31st. `ARCHITECTURE.md` and the
  `Invoice.period_end` field both say so.
- The metering pipeline is fine. The rows are in the database — see them with
  `make psql`.
- This is not a tenant-isolation problem; the isolation suite is green.

### Watch out for

The fix has to hold for a **single-day period**, where `period_start == period_end`.
That case currently returns nothing at all, and it is the one most likely to still be
broken by a fix that looks right.

Finance wants to re-run March billing today, so they need to know whether the totals
can be trusted — write that down in `NOTES.md` as well as fixing the code.
""",
    "definition_of_done": [
        "R1: tests/test_billing.py::test_period_includes_items_on_the_final_day passes",
        "R2: the whole suite is green, with no test skipped, deleted or weakened",
        "R3: a single-day period (period_start == period_end) bills that day",
        "R4: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md explains the root cause, not just the symptom",
    ],
    "focus_paths": ["billing/services.py"],
    "protected_paths": [*STANDARD_PROTECTED, "ci/run_ci.sh"],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_billing.py::test_period_includes_items_on_the_final_day",
            "weight": 3,
            "required": True,
            "description": "The final day of the period is billed",
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
            "kind": CheckKind.PYTEST,
            "target": "tests/test_billing.py::test_a_single_day_period_bills_that_day",
            "weight": 2,
            "required": True,
            "description": "A single-day period works, not just a multi-day one",
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
            "paths": [*STANDARD_PROTECTED, "ci/run_ci.sh"],
            "weight": 0,
            "required": True,
            "description": "Protected test and config files are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.GREP_ABSENT,
            "target": r"created_at__lt\b",
            "paths": ["billing/**/*.py"],
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "The exclusive datetime comparison is gone entirely rather than "
                "patched around by widening the bound"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": "Added a test that pins the inclusive-period contract",
        },
    ],
    "baseline": baseline("ex-001-invoice-drops-final-day"),
    "context_excerpts": [
        {
            "path": "billing/models.py",
            "line_range": "48-78",
            "why": (
                "Invoice.period_end carries help_text saying it is inclusive, which is "
                "the contract the fix has to honour."
            ),
        },
        ARCHITECTURE_EXCERPT,
    ],
    "hints": [
        "Reproduce it narrowly first: `make test-fast`, then read the assertion in "
        "test_period_includes_items_on_the_final_day. What exactly is missing?",
        "Look at the types on both sides of the comparison in "
        "billing/services.py::line_items_for_period. One is a timestamp; the other is not.",
        "Django logs a RuntimeWarning about a naive datetime during the run. That "
        "warning points straight at the coercion that loses the final day.",
    ],
    "grading_notes": """\
**Root cause.** `billing/services.py::line_items_for_period` filters
`created_at__gte=period_start, created_at__lt=period_end`. `created_at` is a
`DateTimeField` while the bounds are `date` objects, so the database coerces each
bound to midnight. Two consequences: `__lt=period_end` excludes everything on the
final day, and a single-day period becomes the empty range `[midnight, midnight)`.

**The expected fix** compares dates against dates --
`created_at__date__gte` / `created_at__date__lte` -- or converts `period_end` to an
aware end-of-day datetime and keeps an exclusive upper bound. Either is correct.

**The most important quality signal:** did they make the *inclusive contract*
explicit, or nudge a bound until the tests went green? `period_end + timedelta(days=1)`
with `__lt` passes everything while leaving the type confusion in place, so the next
person hits the same trap. Treat that as a symptom patch: cap correctness around 70
and set `symptom_patch_suspected`.

**Common wrong turns:** `created_at__lte=period_end` alone (still midnight-coerced,
so it includes one instant of the final day); filtering in Python after the query
(correct numbers, but throws away the index and loads the whole table -- mark
engineering down); editing the fixture in `tests/conftest.py` so the 23:30 item lands
earlier (tampering, hard F); redefining `period_end` as exclusive and updating the
docs (contradicts the brief and would silently change every historical invoice).

**On documentation.** The brief asks whether Finance can trust the totals. A good
`NOTES.md` answers that: the under-billing was systematic, March needs re-running,
and the fix is safe to backfill. An answer that only describes the code change has
missed what was asked.
""",
}


# ---------------------------------------------------------------------------
# ex-002 -- fix a severe latency issue
# ---------------------------------------------------------------------------

EX002 = {
    "slug": "ex-002-project-summary-n-plus-one",
    "exercise_number": 2,
    "title": "The usage dashboard times out for our largest customer",
    "exercise_type": ExerciseType.LATENCY,
    "base_app": BaseApp.TENANTSAAS,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "n_plus_one",
    "time_limit_minutes": 35,
    "expected_time_minutes": 22,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["django", "postgres", "orm", "performance", "n+1"],
    "brief_md": """\
## INC-2410 — `/reporting/usage` times out for Initech

**Severity:** SEV-3
**Reported by:** Support, escalated from Initech

Initech has 400 projects. Their usage dashboard now takes over 30 seconds and the
load balancer cuts it off. Smaller customers are fine, which is why this went
unnoticed for a month.

Our p95 alert never fired because the endpoint is fast for the 95% of tenants who
have fewer than ten projects.

### Reproducing it

```bash
docker compose up -d --wait
make migrate
python bench/bench_queries.py
```

The benchmark seeds a tenant with 40 projects and reports **how many SQL queries**
the summary issues. Query count is the number to watch, not wall-clock: it is
deterministic and it is what actually scales with the customer.

### What "fixed" looks like

The query count must be **small and constant** — it must not grow with the number of
projects. A tenant with 400 projects should cost the same number of round trips as
one with 4.

```bash
make test                      # includes the perf guards
python bench/bench_queries.py  # queries should be <= 3
```

### Constraints

- The response shape must not change. The dashboard is already shipped against it,
  and `tests/test_reporting.py` pins the totals, the ordering, and the fact that a
  project with no usage still appears with zeroes.
- Do not fix this with a cache. The numbers must be live; Finance reconciles against
  them.
""",
    "definition_of_done": [
        "R1: the query count no longer scales with the number of projects",
        "R2: the query count is identical for 12 and 24 projects",
        "R3: bench/bench_queries.py reports 3 queries or fewer",
        "R4: the whole suite is green, with the response shape unchanged",
        "llm: NOTES.md explains why the original cost grew with project count",
    ],
    "focus_paths": ["reporting/services.py"],
    "protected_paths": [*STANDARD_PROTECTED, "bench/**"],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_reporting.py::test_summary_does_not_scale_queries_with_project_count"
            ),
            "weight": 3,
            "required": True,
            "description": "The query count no longer scales with project count",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_reporting.py::test_summary_query_count_is_flat_as_projects_grow",
            "weight": 3,
            "required": True,
            "description": "Doubling the projects does not change the query count",
        },
        {
            "id": "R3",
            "kind": CheckKind.BENCHMARK,
            "target": "python bench/bench_queries.py --json",
            "expect": {"metric": "queries", "op": "<=", "threshold": 3},
            "weight": 3,
            "required": True,
            "description": "The benchmark reports 3 queries or fewer for 40 projects",
        },
        {
            "id": "R4",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions: the response shape and totals are unchanged",
        },
        {
            "id": "R5",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED, "bench/**"],
            "weight": 0,
            "required": True,
            "description": "Tests and the benchmark are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Solved it in SQL with a single aggregate rather than by prefetching "
                "and summing in Python, which would still load every row"
            ),
        },
    ],
    "baseline": baseline("ex-002-project-summary-n-plus-one"),
    "context_excerpts": [
        {
            "path": "reporting/services.py",
            "line_range": "95-125",
            "why": (
                "top_spending_category and tenant_line_item_totals in the same module "
                "show the aggregate style this codebase already uses."
            ),
        },
        {
            "path": "bench/bench_queries.py",
            "line_range": "1-30",
            "why": "Explains why the benchmark measures query counts rather than time.",
        },
    ],
    "hints": [
        "Run `python bench/bench_queries.py` and compare the query count to the "
        "project count. What relationship do you see?",
        "`project_usage_summary` issues one aggregate per project. Django can compute "
        "both aggregates for every project in a single query.",
        "Look at `Count` and `Sum` with a `filter=` argument, and at the "
        "`models_q_for_period` helper that is already in the module but unused.",
    ],
    "grading_notes": """\
**Root cause.** `reporting/services.py::project_usage_summary` loops over
`Project.objects.filter(tenant_id=...)` and issues a separate `.aggregate()` per
project. That is a textbook N+1: 1 query for the projects plus 1 per project, so cost
grows linearly with the customer's size.

**The expected fix** is a single annotated query --
`.annotate(item_count=Count("line_items", filter=Q(...)), item_total=Sum(...))` --
using the `models_q_for_period` helper that is already in the module and left unused
by the regression. That is a real clue, and noticing it is a good sign.

**What to watch for:**

1. **`prefetch_related` plus Python summation.** This does fix the query count and
   will pass R1-R3, but it loads every line item for every project into memory, so it
   trades a query problem for a memory problem. Correct, but mark engineering down and
   say why.
2. **Caching.** The brief forbids it explicitly; Finance reconciles against these
   numbers. If they cached, correctness should reflect that they solved a different
   problem than the one asked.
3. **Dropping the zero-usage projects.** The easy way to make the aggregate simpler is
   an inner join, which silently removes projects with no usage.
   `test_summary_includes_a_project_with_no_usage` catches this; if they broke it and
   did not notice, that is a regression.
4. **Changing the response shape.** The dashboard is shipped against it.

**The strongest signal** is whether they measured. The benchmark exists; a good
`NOTES.md` quotes the before and after query counts rather than asserting the fix is
faster. Someone who says "reduced from 41 queries to 1" has understood the problem.
""",
}


# ---------------------------------------------------------------------------
# ex-003 -- tenant isolation
# ---------------------------------------------------------------------------

EX003 = {
    "slug": "ex-003-export-leaks-across-tenants",
    "exercise_number": 3,
    "title": "SEV-1: a customer downloaded another customer's usage export",
    "exercise_type": ExerciseType.TENANT_ISOLATION,
    "base_app": BaseApp.TENANTSAAS,
    "difficulty": Difficulty.ADVANCED,
    "defect_class": "unscoped_lookup_by_natural_key",
    "time_limit_minutes": 40,
    "expected_time_minutes": 26,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["django", "postgres", "security", "multi-tenancy", "authorization"],
    "brief_md": """\
## INC-2455 — cross-tenant data exposure in project export

**Severity:** SEV-1
**Reported by:** A customer, by email, with a screenshot

Globex downloaded `/reporting/export/website` and got a CSV containing **Acme's**
line items. Both customers happen to have a project called "website".

Legal has been notified. We need the hole closed today and a written account of what
was exposed and to whom.

### Reproducing it

```bash
docker compose up -d --wait
make migrate
make test
```

`tests/test_exports.py` is the relevant suite. Note the asymmetry in what fails —
that is a clue about the mechanism, not noise.

### What we know

- Project slugs are unique **per tenant**, not globally. `projects/models.py` has the
  constraint. Two customers having a "website" project is expected and supported.
- `ARCHITECTURE.md` states the rule: scoping happens in SQL, and
  `TenantScopedQuerySet.for_current_tenant()` **fails closed** by design.
- The middleware is fine. `request.tenant` is correct on every request.

### What "fixed" looks like

1. A tenant can only ever resolve and export **their own** projects.
2. Asking for a slug that belongs to someone else must be **indistinguishable** from
   asking for one that does not exist — otherwise the response becomes an oracle for
   enumerating other customers' projects.
3. The fix generalises. If someone adds another lookup-by-slug next month, it should
   be hard to reintroduce this.

Write down in `NOTES.md` exactly what was exposed, to whom, and whether any other
code path has the same weakness. Legal will read it.
""",
    "definition_of_done": [
        "R1: a tenant never resolves another tenant's project",
        "R2: a slug owned by someone else is indistinguishable from one that does not exist",
        "R3: each tenant's export contains only their own rows",
        "R4: the whole suite is green",
        "R5: bash ci/run_ci.sh exits 0, including the security job",
        "llm: NOTES.md states what was exposed, to whom, and whether anything else is affected",
    ],
    "focus_paths": ["reporting/exports.py"],
    "protected_paths": [*STANDARD_PROTECTED, "ci/run_ci.sh"],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_exports.py::test_resolve_never_returns_another_tenants_project",
            "weight": 4,
            "required": True,
            "description": "A tenant never resolves another tenant's project",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_exports.py::test_resolve_raises_for_a_slug_owned_by_someone_else",
            "weight": 3,
            "required": True,
            "description": "Someone else's slug is indistinguishable from a missing one",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_exports.py::test_export_for_each_tenant_is_disjoint",
            "weight": 3,
            "required": True,
            "description": "Each tenant's export is disjoint from the other's",
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
            "description": "CI passes, including the separate security job",
        },
        {
            "id": "R6",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED, "ci/run_ci.sh"],
            "weight": 0,
            "required": True,
            "description": "Protected test and CI files are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Made the fix structural -- routed the lookup through the scoped "
                "queryset so the next lookup-by-slug is scoped by default -- rather "
                "than adding one tenant_id to one filter"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": "Audited the rest of the codebase for the same weakness",
        },
    ],
    "baseline": baseline("ex-003-export-leaks-across-tenants"),
    "context_excerpts": [
        {
            "path": "tenants/models.py",
            "line_range": "8-40",
            "why": (
                "TenantScopedQuerySet already exists and fails closed. The question is "
                "whether the fix reuses it or bolts a filter on."
            ),
        },
        {
            "path": "projects/models.py",
            "line_range": "28-38",
            "why": "The per-tenant slug uniqueness constraint is what makes this exploitable.",
        },
        ARCHITECTURE_EXCERPT,
    ],
    "hints": [
        "Read the failing tests carefully. Only some of them fail — work out why the "
        "leak is asymmetric between the two tenants.",
        "`reporting/exports.py::resolve_project` looks a project up by slug. What is "
        "missing from that query, given slugs are only unique within a tenant?",
        "The downstream export already filters line items by tenant. That is why the "
        "damage is limited to whichever project object was resolved — and why fixing "
        "the resolution fixes the leak.",
    ],
    "grading_notes": """\
**Root cause.** `reporting/exports.py::resolve_project` does
`Project.objects.filter(slug=slug).first()` with no tenant predicate. Slugs are unique
per tenant, so when two customers share a slug the query returns whichever row the
database yields first -- which may belong to a different tenant. Everything downstream
then faithfully exports that project's data.

**Why the failures are asymmetric, and why it matters.** Default ordering is by name,
so the earlier-created row usually wins. Acme asking for "website" happens to get its
own; Globex gets Acme's. That is exactly how this kind of bug survives review -- it
does not reproduce for the person testing it. A candidate who notices and explains the
asymmetry has understood the mechanism.

**The expected fix** scopes the lookup: `Project.objects.filter(tenant_id=tenant_id,
slug=slug)`, or better `Project.objects.for_tenant(tenant_id).filter(slug=slug)`,
reusing the queryset that already exists.

**The decisive quality signal is whether the fix FAILS CLOSED and GENERALISES.**
Adding one `tenant_id=` to one filter closes this instance. Routing the lookup through
`TenantScopedQuerySet` makes the next lookup scoped by default. Strongly prefer the
second and say so.

**Disqualifying approaches:**

1. **Filtering after the query.** Resolving the project unscoped and then checking
   `project.tenant_id == tenant_id` in Python is *not* a fix in the sense that matters:
   the row already crossed the trust boundary, and a timing or error-message
   difference still leaks existence. Correctness low.
2. **Raising a distinguishable error** ("this project belongs to another tenant").
   Turns the endpoint into an enumeration oracle. `test_resolve_raises_for_a_slug_owned
   _by_someone_else` catches it.
3. **Making slugs globally unique.** Contradicts the shipped constraint and would
   break existing customers.
4. **Editing tests/test_exports.py.** Tampering, hard F.

**On documentation.** This is a SEV-1 with legal involvement. A good `NOTES.md` states
what was exposed (one project's line items, including descriptions and amounts), to
whom, the direction of the leak, and whether any other code path resolves by natural
key without scoping. An answer that only describes the one-line change has not done
the job that was asked.
""",
}


# ---------------------------------------------------------------------------
# ex-004 -- add analytics / statistical features
# ---------------------------------------------------------------------------

EX004 = {
    "slug": "ex-004-implement-revenue-analytics",
    "exercise_number": 4,
    "title": "Finance needs confidence intervals on plan conversion",
    "exercise_type": ExerciseType.ANALYTICS_FEATURES,
    "base_app": BaseApp.TENANTSAAS,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "missing_statistical_implementation",
    "time_limit_minutes": 40,
    "expected_time_minutes": 26,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["python", "statistics", "analytics", "confidence-intervals"],
    "brief_md": """\
## FEAT-882 — put error bars on the conversion dashboard

**Requested by:** Finance
**Priority:** this sprint

Finance reports plan-conversion rates per cohort, and last month they escalated a
"30% drop" that turned out to be 2 conversions out of 6 versus 3 out of 6. They need
**confidence intervals** so a small cohort visibly reads as uncertain instead of as a
crisis.

`reporting/analytics.py` is where the revenue statistics live. `wilson_interval` is
stubbed out and raises `NotImplementedError`; everything else in the module is
implemented and can serve as a guide to the house style.

### What we need

A **Wilson score interval** for a binomial proportion. Not the normal approximation —
Finance's cohorts are small and often near 0% or 100%, where the normal approximation
produces bounds outside `[0, 1]`, which cannot be rendered.

### Reproducing the gap

```bash
docker compose up -d --wait
make test
```

`tests/test_analytics.py` already specifies the behaviour, including the expected
numbers with their derivations in the docstrings. Read them before you start: they
tell you exactly what is required, edge cases included.

### Requirements

- Bounds must stay inside `[0, 1]`, including at 0 of n and n of n.
- A zero-trial cohort must return `Interval(0.0, 0.0)` rather than raising, so a
  brand-new cohort cannot break the dashboard.
- Impossible counts (negative, or more successes than trials) must raise `ValueError`.
- Intervals must narrow as the sample grows.
- No new dependencies. No scipy, no numpy — the `z` constant is already in the module.
""",
    "definition_of_done": [
        "R1: every wilson_interval test passes, including the numeric expectations",
        "R2: the whole suite is green",
        "R3: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md says why Wilson was specified rather than the normal approximation",
    ],
    "focus_paths": ["reporting/analytics.py"],
    "protected_paths": [*STANDARD_PROTECTED, "ci/run_ci.sh"],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_analytics.py::test_wilson",
            "weight": 4,
            "required": True,
            "description": "Every wilson_interval test passes, numerics included",
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
            "paths": [*STANDARD_PROTECTED, "ci/run_ci.sh"],
            "weight": 0,
            "required": True,
            "description": "Protected test and CI files are untouched",
        },
        {
            "id": "R5",
            "kind": CheckKind.GREP_ABSENT,
            "target": r"^\s*(import|from)\s+(numpy|scipy|statsmodels)",
            "paths": ["reporting/**/*.py"],
            "weight": 1,
            "required": True,
            "description": "No new numerical dependencies were introduced",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Handled the floating-point boundary so an all-successes cohort "
                "reports exactly 1.0 rather than 0.9999999999999999"
            ),
        },
    ],
    "baseline": baseline("ex-004-implement-revenue-analytics"),
    "context_excerpts": [
        {
            "path": "reporting/analytics.py",
            "line_range": "60-140",
            "why": (
                "ewma and month_over_month_growth are fully implemented in the same "
                "module and show the expected style: pure functions, explicit edge "
                "cases, documented rationale."
            ),
        },
    ],
    "hints": [
        "Read `tests/test_analytics.py::test_wilson_on_a_clean_half` first. Its "
        "docstring contains the full hand computation for 8 of 16.",
        "The Wilson interval is "
        "(p + z²/2n ± z·sqrt(p(1-p)/n + z²/4n²)) / (1 + z²/n). `Z_95` is already "
        "defined at the top of the module.",
        "At n successes out of n the algebra cancels to exactly 1.0, but in floating "
        "point it lands just below, and `min(1.0, x)` will not clamp that.",
    ],
    "grading_notes": """\
**This is build-shaped, not fix-shaped.** `wilson_interval` raises
`NotImplementedError`; the tests fully specify the behaviour, with the arithmetic
derived in their docstrings. Six tests fail until it is implemented.

**The expected implementation** is the standard Wilson score interval:
`denominator = 1 + z²/n`, `centre = p + z²/(2n)`,
`spread = z·sqrt(p(1-p)/n + z²/(4n²))`, bounds `(centre ∓ spread)/denominator`,
clamped to `[0, 1]`, with `trials == 0` short-circuiting to `Interval(0.0, 0.0)` and
impossible counts raising `ValueError`.

**The interesting detail, and the stretch goal:** at `successes == trials` the
expression cancels to exactly 1.0 algebraically but evaluates to
`0.9999999999999999` in floating point, so `min(1.0, x)` does not clamp it and
`test_wilson_stays_inside_zero_and_one_at_the_extremes` fails. Rounding before
clamping fixes it. A candidate who hits this, diagnoses it as float representation
rather than a formula error, and says so in `NOTES.md` is demonstrating real numerical
care -- weight that heavily in engineering quality.

**Watch for:**

1. **Implementing the normal approximation instead** (`p ± z·sqrt(p(1-p)/n)`). It
   fails the extremes tests and the brief explains why it was rejected. If they did
   this, they did not read the requirement.
2. **Adding scipy or numpy.** Forbidden by the brief and caught by R5. One constant
   does not justify a dependency.
3. **Hardcoding the test values.** Returning `Interval(0.28, 0.72)` for the 8/16 case
   passes that test and fails the others; if any hardcoding survives, that is a
   symptom patch -- set the flag.
4. **Clamping with `max(0, min(1, ...))` only.** Does not fix the float case, because
   the value is already below 1.

**On documentation.** The brief asks why Wilson rather than the normal approximation.
A good answer names the behaviour at small n and near the boundaries. An answer that
just restates the formula has not explained the choice.
""",
}


# ---------------------------------------------------------------------------
# ex-005 -- fix a broken CI/CD pipeline
# ---------------------------------------------------------------------------

EX005 = {
    "slug": "ex-005-ci-red-after-test-reorg",
    "exercise_number": 5,
    "title": "CI has been red since Tuesday and nobody can merge",
    "exercise_type": ExerciseType.CICD_PIPELINE,
    "base_app": BaseApp.TENANTSAAS,
    "difficulty": Difficulty.BEGINNER,
    "defect_class": "ci_selector_and_runtime_mismatch",
    "time_limit_minutes": 25,
    "expected_time_minutes": 15,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["ci", "github-actions", "pytest", "devops"],
    "brief_md": """\
## Nobody can merge — CI is red on every branch

**Reported by:** the whole team, loudly

CI went red on Tuesday and has stayed red on every branch since, including ones with
no changes. Four pull requests are blocked.

The tests themselves are fine. `make test` passes locally and always has.

```bash
docker compose up -d --wait
make migrate
make test    # green
make ci      # red
```

Someone refactored how the test suites are selected on Tuesday afternoon. There is a
`git log` if you want to see what landed.

### About this pipeline

`.github/workflows/ci.yml` is the workflow GitHub runs. `ci/run_ci.sh` is an
executable mirror of the same steps, and it is what `make ci` and our merge gate both
run. **They are supposed to stay in step** — a fix applied to only one of them is not
a fix, and the README says so.

### What "fixed" looks like

1. `bash ci/run_ci.sh` exits 0.
2. The workflow file and the script agree on how suites are selected.
3. The workflow's declared runtime actually runs this codebase. Check whether it does
   before assuming it is fine — it was changed on Tuesday too.
4. No test is deleted, skipped or weakened to get there.

This one should be quick. Say in `NOTES.md` how you would stop the two files drifting
apart again.
""",
    "definition_of_done": [
        "R1: bash ci/run_ci.sh exits 0",
        "R2: the whole suite is still green, with nothing skipped or deleted",
        "R3: neither CI file references a test path that does not exist",
        "R4: the workflow declares a Python version that can run this codebase",
        "llm: NOTES.md proposes how to stop the workflow and the script drifting apart",
    ],
    "focus_paths": ["ci/run_ci.sh", ".github/workflows/ci.yml"],
    "protected_paths": STANDARD_PROTECTED,
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.CMD,
            "target": "bash ci/run_ci.sh",
            "expect": {"exit_code": 0},
            "weight": 4,
            "required": True,
            "description": "The CI pipeline exits 0",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions: nothing was skipped or deleted to go green",
        },
        {
            "id": "R3",
            "kind": CheckKind.GREP_ABSENT,
            "target": r"tests/(security|perf)/",
            "paths": ["ci/*.sh", ".github/workflows/*.yml"],
            "weight": 3,
            "required": True,
            "description": "Neither CI file points at a directory that does not exist",
        },
        {
            "id": "R4",
            "kind": CheckKind.GREP_ABSENT,
            "target": r'python-version:\s*"3\.9"',
            "paths": [".github/workflows/*.yml"],
            "weight": 2,
            "required": True,
            "description": "The workflow no longer pins a runtime that cannot run this code",
        },
        {
            "id": "R5",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": STANDARD_PROTECTED,
            "weight": 0,
            "required": True,
            "description": "The tests themselves are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Proposed a concrete mechanism to keep the workflow and the script in "
                "step, rather than just fixing both by hand"
            ),
        },
    ],
    "baseline": baseline("ex-005-ci-red-after-test-reorg"),
    "context_excerpts": [
        {
            "path": "pytest.ini",
            "line_range": "1-10",
            "why": (
                "Registers the `security` and `perf` markers. The suites are selected "
                "by marker, not by directory -- which is the fact the Tuesday change "
                "got wrong."
            ),
        },
        {
            "path": "README.md",
            "line_range": "55-70",
            "why": "States that ci.yml and ci/run_ci.sh must be changed together.",
        },
    ],
    "hints": [
        "Run `make ci` and read which step fails. The error names the thing that does not exist.",
        "The suites are selected by pytest marker (`-m security`), not by directory. "
        "Check `pytest.ini` for which markers are registered.",
        "Two files changed on Tuesday, not one. Diff `.github/workflows/ci.yml` "
        "against the script and look for anything else that was altered.",
    ],
    "grading_notes": """\
**Two defects, in two files, and both must be fixed.**

1. `ci/run_ci.sh` and `.github/workflows/ci.yml` select the security and perf suites
   by *directory* (`tests/security/`, `tests/perf/`) instead of by *marker*
   (`-m security`, `-m perf`). Those directories do not exist, so pytest exits 4 (a
   usage error, not a test failure) and `set -e` fails the script. This is why `make
   test` is green while `make ci` is red -- a distinction worth checking they
   understood.
2. The workflow pins `python-version: "3.9"`. The codebase uses PEP 604 unions
   (`int | None` in `tenants/context.py`), which are a syntax error before 3.10, so
   the GitHub job could not even import the app. This one cannot be caught by running
   the script locally -- only by reading the workflow. Candidates who fix only the
   selector have done half the job, and R4 catches it.

**The expected fix** restores `-m security` and `-m perf` in both files and restores
`python-version: "3.12"`.

**Watch for:**

1. **Creating `tests/security/` and `tests/perf/` directories** and moving tests into
   them. This makes CI green and is not automatically wrong, but it contradicts
   `pytest.ini`'s marker registration and the rest of the suite's conventions, and it
   is a much larger change than the situation calls for. If they did this, judge
   whether they justified it -- an unjustified reorganisation during an outage is poor
   judgement even when it works.
2. **Deleting the failing steps** from the script. Makes it exit 0 while removing the
   security gate entirely. R3 will pass and R1 will pass, so lean on the suite check
   and your own reading of the diff: this is the worst outcome here and should score
   very low on correctness despite green checks. Set `symptom_patch_suspected`.
3. **Fixing only `ci/run_ci.sh`.** R1 passes, R3 fails. The README says the two files
   move together.
4. **Leaving the Python pin alone.** Easy to miss because it cannot be reproduced
   locally. Not fatal, but a candidate who read both files should have caught it.

**On documentation.** The brief asks how to stop the two files drifting. Good answers:
generate one from the other, have the workflow call the script rather than duplicating
the steps, or add a test asserting the step lists match. "Be more careful" is not an
answer.
""",
}


# ---------------------------------------------------------------------------
# ex-006 -- fix a critical bug fast (second of two on this base app)
# ---------------------------------------------------------------------------

EX006 = {
    "slug": "ex-006-invoice-rebuild-double-bills",
    "exercise_number": 6,
    "title": "SEV-1: re-running billing doubled 1,900 invoices",
    "exercise_type": ExerciseType.CRITICAL_BUG,
    "base_app": BaseApp.TENANTSAAS,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "non_idempotent_upsert",
    "time_limit_minutes": 30,
    "expected_time_minutes": 18,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["django", "postgres", "billing", "idempotency", "orm"],
    "brief_md": """\
## INC-2504 — customers were charged twice

**Severity:** SEV-1
**Reported by:** Support (14 tickets in 40 minutes), escalated by Finance

The April billing run failed partway through last night, so it was re-run at 06:10.
Every invoice that had already been written before the failure is now **exactly double**
what it should be. 1,900 invoices are affected and about 40 have already been sent.

There is **one** invoice row per tenant per period — no duplicates. The numbers on the
existing rows are wrong.

### Reproducing it

```bash
docker compose up -d --wait
make migrate
make test
```

`tests/test_billing.py::test_rebuilding_leaves_the_totals_unchanged` is the shortest
route to it.

### What we know

- A re-run is supposed to be safe. Billing has always been documented as re-runnable —
  `build_invoice` says "create or refresh", and it is called from a retry path.
- `test_build_invoice_is_idempotent` **passes**, and passed on the commit that shipped
  this. Do not take it as evidence the job is idempotent; read what it actually
  asserts.
- The line items themselves are fine. The metering data was never touched.

### What "fixed" looks like

1. Re-running the job any number of times leaves an invoice identical to running it
   once.
2. A re-run still picks up usage that arrived since the last run — exactly once. This
   is the half that a naive fix breaks.
3. No test is deleted, skipped or weakened.

Finance needs to know, in `NOTES.md`, **which invoices to correct and how** — they have
to decide before 09:00 whether to re-issue or credit. State whether a plain re-run is
now safe on the affected rows.
""",
    "definition_of_done": [
        "R1: tests/test_billing.py::test_rebuilding_leaves_the_totals_unchanged passes",
        "R2: a rebuild counts usage that arrived since the last run exactly once",
        "R3: the whole suite is green, with nothing skipped, deleted or weakened",
        "R4: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md tells Finance which invoices are wrong and how to correct them",
    ],
    "focus_paths": ["billing/services.py"],
    "protected_paths": [*STANDARD_PROTECTED, "ci/run_ci.sh"],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_billing.py::test_rebuilding_leaves_the_totals_unchanged",
            "weight": 3,
            "required": True,
            "description": "Re-running the job leaves the totals unchanged",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_billing.py::test_rebuilding_counts_usage_that_arrived_since_exactly_once"
            ),
            "weight": 3,
            "required": True,
            "description": "A rebuild still picks up late-arriving usage, exactly once",
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
            "paths": [*STANDARD_PROTECTED, "ci/run_ci.sh"],
            "weight": 0,
            "required": True,
            "description": "Protected test and CI files are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.GREP_ABSENT,
            "target": r"\+=",
            "paths": ["billing/services.py"],
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "The accumulation is gone rather than guarded by a flag or a first-run check"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Said how the 1,900 already-written invoices get corrected, not just "
                "how the code changed"
            ),
        },
    ],
    "baseline": baseline("ex-006-invoice-rebuild-double-bills"),
    "context_excerpts": [
        {
            "path": "billing/models.py",
            "line_range": "48-85",
            "why": (
                "Invoice carries unique_invoice_period_per_tenant, which is why the "
                "bug produced one wrong row rather than two rows."
            ),
        },
        {
            "path": "tests/test_billing.py",
            "line_range": "92-98",
            "why": (
                "test_build_invoice_is_idempotent passes throughout. Reading what it "
                "asserts -- one row, same pk, nothing about the amounts -- is what "
                "explains how this shipped."
            ),
        },
    ],
    "hints": [
        "Run `make test-fast` and read the failing assertion. It compares the totals "
        "after one run against the totals after two.",
        "Look at how `build_invoice` writes the row in `billing/services.py`. What "
        "happens on the second call, when the row already exists?",
        "`get_or_create` returns a `created` flag; the branch taken when it is False "
        "is doing arithmetic on the values already stored.",
    ],
    "grading_notes": """\
**Root cause.** `billing/services.py::build_invoice` calls `get_or_create` and then, on
the not-created branch, **adds** the freshly computed totals to the values already on
the row. The first run is correct; every subsequent run inflates the invoice by another
period's worth of usage. The unique constraint guarantees one row per tenant and period,
which is exactly why this looked like "invoices are wrong" rather than "invoices are
duplicated" and why nobody suspected the retry.

**The expected fix** is `update_or_create` with the computed totals in `defaults`, so
the row is *replaced* rather than adjusted. A compute-then-overwrite `.save()` on the
fetched row is equally correct.

**The trap, and the main thing to judge.** A fix that makes the invoice immune to
re-running by skipping the write when the row exists (`if created:` / an
`already_billed` guard / `objects.filter(...).exists()` and return) passes R1 and the
idempotency test, and **fails R2**: the job then cannot pick up late-arriving usage at
all, which silently under-bills instead of over-billing. If R2 fails, this is almost
certainly what happened. Note that the candidate was warned about this in the brief, so
tripping it is a reading failure as much as a design one.

**Watch for:**

1. **Recomputing from scratch but keeping `+=` behind a "first run" flag** — a new
   column or a status check that makes the arithmetic conditional. Passes both tests and
   leaves a footgun. S1 (no `+=` left in the module) is the mechanical signal; weigh
   engineering down and say why.
2. **Making the totals a property computed on read** rather than stored. Defensible, but
   it changes the model and the invoice is supposed to be a *finalised* record of what
   was billed — a historical invoice must not silently change when old line items are
   corrected. If they did this, judge whether they noticed that trade-off.
3. **Editing `test_build_invoice_is_idempotent`** so it covers amounts. Tempting, and it
   is a protected file: tampering, hard F. The right move is to leave it and note that
   it was too weak.
4. **Fixing the data in a migration.** Not asked for and risky in the middle of an
   incident, but proposing it in NOTES.md is exactly right.

**On documentation.** The brief asks which invoices to correct and how. A good answer
states that the affected rows are those written before the first run failed, that the
correction is a re-run **once the code is fixed** (because the fix makes a rebuild
authoritative rather than additive), that the 40 already-sent invoices need re-issuing
or crediting as a business decision, and that nothing is wrong with the underlying line
items. An answer that only describes the code change has not done the job that was
asked, however good the fix is.
""",
}


# ---------------------------------------------------------------------------
# ex-007 -- severe latency (second of two on this base app)
# ---------------------------------------------------------------------------

EX007 = {
    "slug": "ex-007-invoice-totals-stream-every-row",
    "exercise_number": 7,
    "title": "The monthly billing run OOMs on our largest tenant",
    "exercise_type": ExerciseType.LATENCY,
    "base_app": BaseApp.TENANTSAAS,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "aggregate_in_python",
    "time_limit_minutes": 35,
    "expected_time_minutes": 21,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["django", "postgres", "orm", "performance", "memory"],
    "brief_md": """\
## INC-2588 — the billing worker is killed on the 1st of the month

**Severity:** SEV-3
**Reported by:** Platform, from the worker's restart log

The billing worker gets OOM-killed partway through the monthly run. It restarts, picks
up where it left off, and gets killed again. It finishes eventually, after four or five
restarts, which is why this has been tolerated for two months.

It is always the same tenant that kills it — our largest, about 600,000 line items in a
month. Small tenants are instant. Memory climbs steadily while that one tenant is being
billed and the process dies before the invoice is written.

The totals it produces are **correct**. This is purely about what it costs to produce
them.

### Reproducing it

```bash
docker compose up -d --wait
make migrate
python bench/bench_invoice.py
```

The benchmark totals a period for two tenants — 250 line items and 5,000 — and reports
**how many rows were fetched from the database**, not wall-clock time. Rows are the
number that matters: this is a memory problem, and the row count is what grows.

### What "fixed" looks like

The rows fetched must be **small and independent of the tenant's usage**. A tenant with
600,000 line items should cost the same handful of rows as one with 250.

```bash
python bench/bench_invoice.py   # rows_large small, rows_growth at or near 1.0
make test                       # totals unchanged
```

### Constraints

- **The totals must not change.** `tests/test_billing.py` pins them exactly, including
  how credits offset charges and what an empty period returns. Finance reconciles
  against these numbers.
- Do not add a cache, and do not change what `InvoiceTotals` contains — the invoice
  writer and the API both read it.
- Do not paginate or chunk the loop. Processing 600,000 rows in batches of 1,000 still
  moves 600,000 rows; it lowers the peak but not the cost, and the cost is the problem.

Before you start, run the benchmark and look at **both** numbers it reports. One of them
does not move at all between the broken version and a correct fix. Say in `NOTES.md`
which one, and why that is the whole point.
""",
    "definition_of_done": [
        "R1: rows fetched for the large tenant is small and does not scale with usage",
        "R2: rows fetched is essentially identical for 250 and 5,000 line items",
        "R3: the whole suite is green and every total is unchanged",
        "R4: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md explains why rows, not queries, was the metric that mattered -- "
        "the query count is 1 before and 1 after",
    ],
    "focus_paths": ["billing/services.py"],
    "protected_paths": [*STANDARD_PROTECTED, "bench/**", "ci/run_ci.sh"],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.BENCHMARK,
            "target": "python bench/bench_invoice.py --json",
            "expect": {"metric": "rows_large", "op": "<=", "threshold": 8},
            "weight": 4,
            "required": True,
            "description": "Totalling 5,000 line items fetches at most 8 rows",
        },
        {
            "id": "R2",
            "kind": CheckKind.BENCHMARK,
            "target": "python bench/bench_invoice.py --json",
            "expect": {"metric": "rows_growth", "op": "<=", "threshold": 1.5},
            "weight": 3,
            "required": True,
            "description": "Twenty times the usage costs the same rows",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions: every total is unchanged",
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
            "paths": [*STANDARD_PROTECTED, "bench/**", "ci/run_ci.sh"],
            "weight": 0,
            "required": True,
            "description": "Tests and the benchmark are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Aggregated in SQL rather than reducing the rows fetched by iterating "
                "in batches or using .only()/.values(), which still scale with usage"
            ),
        },
    ],
    "baseline": baseline("ex-007-invoice-totals-stream-every-row"),
    "context_excerpts": [
        {
            "path": "reporting/services.py",
            "line_range": "42-73",
            "why": (
                "project_usage_summary and tenant_line_item_totals in the sibling "
                "module show the conditional-aggregate style this codebase already "
                "uses, including Sum with a filter= argument."
            ),
        },
        {
            "path": "bench/bench_invoice.py",
            "line_range": "1-30",
            "why": (
                "Explains why the benchmark counts rows rather than queries, which is "
                "the distinction the whole exercise turns on."
            ),
        },
    ],
    "hints": [
        "Run `python bench/bench_invoice.py` and compare rows fetched against the "
        "line-item counts. What is the relationship?",
        "`compute_totals` in `billing/services.py` iterates the queryset to add up "
        "`amount_cents`. Every row it adds up had to be sent, decoded and turned into "
        "a model instance first.",
        "The database can compute all three numbers. Look at `.aggregate()`, and at "
        "`Sum` with a `filter=` argument for the charges/credits split -- "
        "`reporting/services.py` already does this.",
    ],
    "grading_notes": """\
**Root cause.** `billing/services.py::compute_totals` evaluates the period queryset and
sums `amount_cents` in Python, then calls `.count()`. Every line item in the period is
sent over the wire and instantiated as a model object in order to produce three
integers, so the worker's memory is proportional to the tenant's usage. At 600,000 line
items that is what kills the process.

**The expected fix** is one aggregate query:

    .aggregate(
        charges=Sum("amount_cents", filter=Q(amount_cents__gt=0)),
        credits=Sum("amount_cents", filter=Q(amount_cents__lt=0)),
        line_items=Count("id"),
    )

with `or 0` coalescing, because `Sum` returns NULL rather than 0 when nothing matches
the filter. `reporting/services.py` uses this exact pattern, so it is the house style
rather than a clever trick.

**Why this exercise exists separately from the N+1 one, and the measured fact that
makes it work.** The query count is **identical before and after: one query either
way.** Not "nearly the same" -- the same. The broken version issues a single SELECT and
then calls `.count()`, which short-circuits to `len()` of the already-populated result
cache rather than issuing a second query, so fetching every row makes the count free.
A candidate who reaches for query count as their metric will measure 1 against 1 and
conclude there is nothing to fix.

What collapses is rows transferred: **5,000 to 1** in the benchmark (measured), and
600,000 to 1 in production. **The strongest signal is whether they understood which
quantity was scaling**, and `NOTES.md` is where that shows. Someone who writes "one
query before, one query after, 5,000 rows before, 1 after" has understood the problem
completely.

**Watch for:**

1. **`.iterator()` or manual chunking.** This is the most likely wrong answer and it is
   *not* nonsense -- it genuinely lowers peak memory and would stop the OOM. But it
   still fetches every row, so cost stays proportional to usage and `rows_growth` stays
   at ~20. R1 and R2 both fail. If they did this, they solved the symptom (the process
   dying) rather than the cause (fetching data to compute a scalar). The brief rules it
   out explicitly, so also weigh whether they read the constraints.
2. **`.values_list("amount_cents", flat=True)` and summing that.** Cheaper per row --
   no model instances -- and a real improvement, but still one row per line item. Same
   verdict as above: R1/R2 fail, and the reasoning is closer than chunking.
3. **Two aggregate queries instead of one** (`filter(amount_cents__gt=0).aggregate(...)`
   twice). Correct, passes everything, marginally less elegant. Do not mark this down
   much; it is a readable solution and the row cost is what mattered.
4. **Losing the credits/charges distinction.** `Sum("amount_cents")` alone gives the
   net, and `subtotal_cents` must be charges only. `test_totals_sum_positive_charges_into_the_subtotal`
   and `test_totals_apply_credits_to_the_total` catch it.
5. **Returning `None` instead of `0` for an empty period.** The classic `Sum`-is-NULL
   mistake; `test_totals_are_zero_for_a_period_with_no_usage` catches it.
6. **Caching**, which the brief forbids -- Finance reconciles against live numbers.

**On documentation.** A good `NOTES.md` quotes the benchmark before and after (5,000
rows -> 1, growth 20.0 -> 1.0, queries 1 -> 1), says plainly that the query count was
never the problem, and connects that to the OOM. An answer that says "optimised the
query" without naming what was scaling has not demonstrated the understanding this
exercise is testing.
""",
}


# ---------------------------------------------------------------------------
# ex-008 -- broken/flaky CI (second of two on this base app)
# ---------------------------------------------------------------------------

EX008 = {
    "slug": "ex-008-ci-flakes-on-tied-categories",
    "exercise_number": 8,
    "title": "CI fails about half the time and re-running usually fixes it",
    "exercise_type": ExerciseType.CICD_PIPELINE,
    "base_app": BaseApp.TENANTSAAS,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "hash_seed_dependency",
    "time_limit_minutes": 35,
    "expected_time_minutes": 22,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["ci", "pytest", "flaky", "determinism", "python"],
    "brief_md": """\
## CI is flaky and the team has started re-running it on reflex

**Reported by:** four engineers, three separate Slack threads

`tests/test_reporting.py::test_top_category_breaks_ties_alphabetically` fails roughly
half the time. Hit re-run and it usually goes green, so for two weeks everybody has
been hitting re-run.

It is now blocking a release train, and somebody pointed out that we do not actually
know it is the *test* that is flaky.

### Reproducing it

```bash
docker compose up -d --wait
make migrate
bash ci/run_ci.sh          # fails maybe one run in two
bash ci/run_ci.sh          # ...and passes the next
```

A single `make test` run tells you almost nothing here — it is a coin flip. Run it
several times.

### What we know

- The failure is **consistent within one run**: when it fails, it fails the same way,
  and `test_top_category_is_deterministic_across_repeated_calls` — which calls the same
  function 25 times in a row — **passes every single time**. Whatever varies, it does
  not vary between calls inside one process.
- `ci/run_ci.sh` exports the environment CI runs with. Read it.
- Nothing in `reporting/` has changed for three weeks, so "it started recently" is about
  when the tie appeared in the data, not about a code change.

### What "fixed" looks like

1. `test_top_category_breaks_ties_alphabetically` passes **20 runs out of 20**, in the
   CI environment. One green run is not evidence.
2. The rest of the suite stays green.
3. The test is not deleted, skipped, marked `xfail`, retried, or given a fixed seed.

A retry wrapper would make CI green and is not a fix. In `NOTES.md`, say what was
actually nondeterministic, why it was invisible inside a single process, and how you
would stop this class of bug reaching CI again.
""",
    "definition_of_done": [
        "R1: the tie-break test passes 20 consecutive runs under the CI environment",
        "R2: the whole suite is green, with nothing skipped, deleted or retried",
        "R3: bash ci/run_ci.sh exits 0",
        "R4: no test file, pytest.ini or CI file was modified",
        "llm: NOTES.md identifies the nondeterminism and why one process could not see it",
    ],
    "focus_paths": ["reporting/services.py"],
    "protected_paths": [*STANDARD_PROTECTED, "ci/run_ci.sh", ".github/workflows/ci.yml"],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.FLAKE_REPEAT,
            "target": "tests/test_reporting.py::test_top_category_breaks_ties_alphabetically",
            "repeat": 20,
            "weight": 4,
            "required": True,
            "description": "The tie-break test passes 20 consecutive CI-environment runs",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST_SUITE,
            "weight": 3,
            "required": True,
            "description": "No regressions: nothing was skipped, deleted or retried",
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
            # Matches a *pin* to a fixed seed, not the pristine
            # `export PYTHONHASHSEED=random` that ci/run_ci.sh has always carried.
            "kind": CheckKind.GREP_ABSENT,
            "target": r"PYTHONHASHSEED\s*[:=]\s*[\"']?[0-9]",
            "paths": [
                "ci/*.sh",
                ".github/workflows/*.yml",
                "pytest.ini",
                "Makefile",
                "conftest.py",
                "tests/conftest.py",
            ],
            "weight": 2,
            "required": True,
            "description": (
                "The hash seed was not pinned to hide the nondeterminism instead of removing it"
            ),
        },
        {
            "id": "R5",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED, "ci/run_ci.sh", ".github/workflows/ci.yml"],
            "weight": 0,
            "required": True,
            "description": "Tests and both CI files are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.GREP_ABSENT,
            "target": r"\bset\(",
            "paths": ["reporting/services.py"],
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": "The order-dependent set iteration is gone entirely",
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Proposed a way to catch order-dependence before CI does, rather than "
                "only fixing this instance"
            ),
        },
    ],
    "baseline": baseline("ex-008-ci-flakes-on-tied-categories"),
    "context_excerpts": [
        {
            "path": "ci/run_ci.sh",
            "line_range": "10-20",
            "why": (
                "Exports PYTHONHASHSEED=random to match CI. That one line is the "
                "difference between a run that passes and a run that does not."
            ),
        },
        {
            "path": "tests/test_reporting.py",
            "line_range": "155-168",
            "why": (
                "The tie fixture gives two kinds identical totals, and the "
                "repeated-calls test passing while the tie test fails is the clue that "
                "the variation is per-process, not per-call."
            ),
        },
    ],
    "hints": [
        "Run `bash ci/run_ci.sh` three or four times. Note that the failure is stable "
        "within a run and varies between runs -- that narrows it a long way.",
        "Read the environment `ci/run_ci.sh` exports before running pytest. One of "
        "those variables changes how Python behaves, not how pytest behaves.",
        "`top_spending_category` in `reporting/services.py` iterates a `set` to find "
        "the winner. Set iteration order for strings depends on hash randomisation, "
        "which is fixed for the life of a process and different in the next one.",
    ],
    "grading_notes": """\
**Root cause.** `reporting/services.py::top_spending_category` builds a `dict` of totals
per kind, then iterates `set(totals)` and keeps the first kind with a strictly greater
total. When two kinds tie -- which the `tied_categories` fixture arranges -- the winner
is whichever the set yields first. Set iteration order for strings depends on
`PYTHONHASHSEED`, which CPython randomises per process. `ci/run_ci.sh` exports
`PYTHONHASHSEED=random` explicitly, so CI is guaranteed to vary.

That is also why the defect is invisible to
`test_top_category_is_deterministic_across_repeated_calls`: within one process the hash
seed is fixed, so 25 consecutive calls agree with each other. They are consistently
*either* right or wrong. Any candidate who used that test as evidence the function is
deterministic drew the wrong conclusion from it, and the brief points at the distinction.

**The expected fix** restores a total order:
`sorted(totals.items(), key=lambda pair: (-pair[1], pair[0]))` and take the first, or
`min(totals.items(), key=lambda pair: (-pair[1], pair[0]))`. Any fix that makes the
result independent of iteration order is correct; the tie must resolve alphabetically
because that is what the test and the docstring specify.

**Disqualifying approaches:**

1. **Pinning `PYTHONHASHSEED=0`** in `ci/run_ci.sh`, the workflow, `pytest.ini` or the
   `Makefile`. This makes CI green while leaving the function order-dependent, so
   production still returns whichever answer that process happens to produce -- and the
   next reader has no idea the pin is load-bearing. R4 catches it. This is the worst
   outcome and should score very low on correctness even though R1 would pass; set
   `symptom_patch_suspected`.
2. **Retry wrappers** -- `pytest-rerunfailures`, a loop, `@pytest.mark.flaky`. Hides a
   real nondeterminism in shipped code. The brief forbids it.
3. **Editing the test** to accept either kind, or to stop creating a tie. Tampering on a
   protected file, hard F. Weakening the assertion is the same thing by other means.
4. **Sorting only by `-total`** without the name tie-break. `sorted` is stable, so the
   result then depends on `dict` insertion order, which depends on the order rows came
   back from the database -- better, but still not specified anywhere and still capable
   of changing. R1 will usually pass, which makes this the most likely way to get a
   green run with a fix that is not quite right. Notice it.

**What separates a good answer.** The mechanism has three parts and a strong `NOTES.md`
names all three: a tie makes two orderings possible, `set` iteration exposes hash order,
and hash randomisation is per-process so a single run can never reveal it. The stretch
goal is proposing how to catch the class rather than the instance -- running the suite
under two different fixed seeds in CI, a lint rule against iterating sets where order is
consumed, or an assertion inside the function that the top two totals are not tied
without a documented tie-break.

**On timing.** The reproduction is inherently probabilistic, so expect the clock to show
more elapsed time than the diff size suggests. Do not read a long elapsed time here as
inefficiency; running it five times to characterise the failure is the correct first
move and the brief asks for it.
""",
}


EXERCISES: list[dict] = [EX001, EX002, EX003, EX004, EX005, EX006, EX007, EX008]
