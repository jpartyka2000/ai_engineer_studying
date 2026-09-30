"""Exercises built on the ``tenantsaas`` base application.

Each entry is a ``(base_app, mutations)`` pair rather than its own codebase, which
is what makes a catalog of fifty exercises authorable.

The ``baseline`` on each exercise is **measured by the verification harness**, never
guessed. Verification asserts exact set equality against it: a superset of failing
tests means the injected defect broke more than intended, which makes the exercise
unfair and renders the regression check meaningless.
"""

from apps.workspace.enums import BaseApp, CheckKind, Database, Difficulty, ExerciseType

# Measured on the pristine template, then re-measured after applying the mutation.
# 32 tests total: 9 fail under the defect, 23 keep passing.
EX001_FAILING = [
    "tests/test_api.py::test_usage_summary_returns_period_totals",
    "tests/test_api.py::test_create_invoice_returns_201_with_the_invoice",
    "tests/test_billing.py::test_period_includes_items_on_the_final_day",
    "tests/test_billing.py::test_period_returns_exactly_the_expected_count",
    "tests/test_billing.py::test_totals_sum_positive_charges_into_the_subtotal",
    "tests/test_billing.py::test_totals_apply_credits_to_the_total",
    "tests/test_billing.py::test_totals_count_every_line_item",
    "tests/test_billing.py::test_a_single_day_period_bills_that_day",
    "tests/test_billing.py::test_build_invoice_persists_the_totals",
]

EX001_PASSING = [
    "tests/test_api.py::test_healthz_needs_no_api_key",
    "tests/test_api.py::test_a_missing_api_key_is_rejected",
    "tests/test_api.py::test_an_unknown_api_key_is_rejected",
    "tests/test_api.py::test_an_inactive_tenant_is_rejected",
    "tests/test_api.py::test_projects_lists_only_the_callers_projects",
    "tests/test_api.py::test_usage_summary_rejects_bad_periods[params0]",
    "tests/test_api.py::test_usage_summary_rejects_bad_periods[params1]",
    "tests/test_api.py::test_usage_summary_rejects_bad_periods[params2]",
    "tests/test_api.py::test_usage_summary_rejects_bad_periods[params3]",
    "tests/test_api.py::test_create_invoice_rejects_a_non_json_body",
    "tests/test_api.py::test_create_invoice_rejects_a_get",
    "tests/test_api.py::test_invoices_lists_only_the_callers_invoices",
    "tests/test_billing.py::test_period_includes_items_on_the_first_day",
    "tests/test_billing.py::test_period_excludes_items_after_the_period",
    "tests/test_billing.py::test_totals_are_zero_for_a_period_with_no_usage",
    "tests/test_billing.py::test_build_invoice_is_idempotent",
    "tests/test_billing.py::test_invoices_never_mix_tenants",
    "tests/test_tenants.py::test_for_current_tenant_scopes_to_the_active_tenant",
    "tests/test_tenants.py::test_for_current_tenant_fails_closed_without_a_tenant",
    "tests/test_tenants.py::test_for_tenant_scopes_explicitly",
    "tests/test_tenants.py::test_middleware_clears_the_context_after_a_request",
    "tests/test_tenants.py::test_tenant_context_restores_the_previous_value",
    "tests/test_tenants.py::test_project_slugs_are_unique_per_tenant_not_globally",
]


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
that **every invoice is missing the last day of the period**. Across all tenants
that is roughly $40k of usage that was never billed.

One customer noticed the other direction too: they queried
`/usage?period_start=2026-03-10&period_end=2026-03-10` for a single day and got
zero, even though they know they had usage that day.

### Reproducing it

```bash
docker compose up -d --wait
make migrate
make seed
make test
```

Nine tests fail. `tests/test_billing.py::test_period_includes_items_on_the_final_day`
is the most direct expression of the problem.

### What we know

- Billing periods are **inclusive at both ends**. An invoice for 1–31 March covers
  usage recorded right up to `23:59:59` on the 31st. `ARCHITECTURE.md` and the
  `Invoice.period_end` field both say so.
- The metering pipeline is fine. The rows are in the database — you can see them
  with `make psql`.
- This is not a tenant-isolation problem; the isolation suite is green.

### Watch out for

Whatever you change, the fix has to hold for a **single-day period**, where
`period_start == period_end`. That case is currently returning nothing at all, and
it is the one most likely to still be broken by a fix that looks right.

Finance wants to re-run March billing today, so they need to know whether the
totals can be trusted — write that down in `NOTES.md` as well as fixing the code.
""",
    "definition_of_done": [
        "R1: tests/test_billing.py::test_period_includes_items_on_the_final_day passes",
        "R2: the whole suite is green, with no test skipped, deleted or weakened",
        "R3: a single-day period (period_start == period_end) bills that day",
        "R4: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md explains the root cause, not just the symptom",
    ],
    "focus_paths": ["billing/services.py"],
    "protected_paths": [
        "tests/**",
        "pytest.ini",
        "ci/run_ci.sh",
    ],
    "mutations": [
        {"op": "apply_patch", "patch": "mutation.patch"},
    ],
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
            "paths": ["tests/**", "pytest.ini", "ci/run_ci.sh"],
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
                "The exclusive datetime comparison is gone entirely, rather than "
                "being patched around by widening the bound"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 1,
            "required": False,
            "stretch": True,
            "description": (
                "Added a test of their own that pins the inclusive-period contract, "
                "and it fails against the unfixed code"
            ),
        },
    ],
    "baseline": {
        "failing_nodes": EX001_FAILING,
        "passing_nodes": EX001_PASSING,
        "metrics": {},
    },
    "context_excerpts": [
        {
            "path": "billing/models.py",
            "line_range": "48-78",
            "why": (
                "Invoice.period_end carries help_text saying it is inclusive, which is "
                "the contract the fix has to honour."
            ),
        },
        {
            "path": "ARCHITECTURE.md",
            "line_range": "55-65",
            "why": "States the inclusive-period rule and flags it as the easiest thing to break.",
        },
    ],
    "hints": [
        "Reproduce it narrowly first: `make test-fast` then read the assertion in "
        "test_period_includes_items_on_the_final_day. What exactly is missing?",
        "Look at the types on both sides of the comparison in "
        "billing/services.py::line_items_for_period. One is a timestamp; the other is not.",
        "Django logs a RuntimeWarning about a naive datetime during the test run. "
        "That warning is pointing straight at the coercion that loses the final day.",
    ],
    "grading_notes": """\
**Root cause.** `billing/services.py::line_items_for_period` filters
`created_at__gte=period_start, created_at__lt=period_end`. `created_at` is a
`DateTimeField` while the bounds are `date` objects, so the database coerces each
bound to midnight. Two consequences: `__lt=period_end` excludes everything on the
final day, and a single-day period becomes the empty range
`[midnight, midnight)`.

**The expected fix** is to compare dates against dates —
`created_at__date__gte=period_start, created_at__date__lte=period_end` — or,
equivalently, to convert `period_end` to an aware datetime at the end of that day
and keep an exclusive upper bound. Either is correct.

**The single most important quality signal:** did they make the *inclusive contract*
explicit, or did they just nudge a bound until the tests went green? A fix of
`period_end + timedelta(days=1)` with `__lt` passes every test while leaving the
type confusion in place, so the next person hits the same trap. Treat that as a
symptom patch: cap correctness at ~70 and set `symptom_patch_suspected`.

**Common wrong turns:**

1. `created_at__lte=period_end` alone — still midnight-coerced, so it now includes
   exactly one instant of the final day and almost nothing else. Tests still fail;
   if they stopped here they did not re-run.
2. Filtering in Python after the query (`[i for i in items if i.created_at.date() <= period_end]`)
   — produces correct numbers but throws away the index and loads the whole table.
   Note it as a correctness-by-accident outcome and mark engineering down.
3. Editing the fixture in `tests/conftest.py` so the 23:30 item lands earlier in the
   day. That is tampering with a protected file and is a hard F.
4. Changing `Invoice.period_end`'s semantics to exclusive and updating the docs to
   match. This contradicts the brief, `ARCHITECTURE.md` and Finance's expectation,
   and would silently change every historical invoice. Correctness low.

**On documentation.** The brief explicitly asks whether Finance can trust the
totals. A good `NOTES.md` answers that directly — the under-billing was systematic,
so March needs re-running, and the fix is safe to backfill. An answer that only
describes the code change has missed what was asked.
""",
}


EXERCISES: list[dict] = [EX001]
