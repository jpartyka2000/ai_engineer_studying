# Packet pre-briefs

One factual summary per packet, to cut reading time. For each item: what was asked, what
the checks report, what the diff does, and what the writeup covers.

**No letters, no scores, no verdicts, and no ranking.** Nothing here says whether a
submission is good, and items are listed alphabetically within each exercise, so position
carries no meaning. Coverage statements ("does not mention X") are checklist facts against
what the brief asked for, not judgements about whether X mattered.

These are a shortcut, not a substitute. If a pre-brief and a packet disagree, the packet
is the truth — it is what the grader was sent.

---

## SEV-2: March invoices are short by a day's usage
*30-minute box, author's estimate 19 minutes*

**Asked:** the final-day test passes; the suite stays green with nothing skipped, deleted
or weakened; a single-day period (`period_start == period_end`) bills that day;
`bash ci/run_ci.sh` exits 0; and `NOTES.md` explains the root cause rather than the
symptom. The brief adds: *"Finance wants to re-run March billing today, so they need to
know whether the totals can be trusted — write that down in `NOTES.md`."* It also warns
the fix has to hold for a single-day period.

**Protected:** `tests/**`, `pytest.ini`, `ci/run_ci.sh`.
**Stretch:** S1 (mechanical) — no `created_at__lt` left anywhere in `billing/`.
S2 (model-judged) — added a test pinning the inclusive-period contract.

### item-707c — 14 of 30 minutes, 2 commits, 2 files, +18 −16
**Checks:** 5/5 required PASSED. **S1 FAILED** — `created_at__lt` still present at
`billing/services.py:39`.
**Diff:** adds `timedelta` to the `datetime` import and changes the upper bound to
`created_at__lt=period_end + timedelta(days=1)`. `created_at__gte=period_start` is
unchanged. No date-typed comparison is introduced.
**Writeup:** 7 headings, ~1,000 characters. Says the upper bound was exclusive so the
final day fell outside the range, and describes the +1-day change. Under alternatives,
says it is a one-line change that keeps the existing half-open range shape, which is "the
usual way to write these". Does not mention that `created_at` is a `DateTimeField` while
the bounds are `date` objects, or midnight coercion. Does not address whether Finance can
trust the totals. "What I verified" is one sentence: the two tests pass, the suite is
green, CI exits 0.

### item-bcae — 19 of 30 minutes, 3 commits, 3 files, +162 −16
**Checks:** 5/5 required PASSED. S1 PASSED. S2 model-judged.
**Diff:** changes the filter in `line_items_for_period` from
`created_at__gte` / `created_at__lt` to `created_at__date__gte` / `created_at__date__lte`,
and restores a 4-line comment stating that comparing a timestamp to `date` bounds makes
the database coerce them to midnight. Adds `tests/test_billing_period_contract.py` with
four tests: last minute of the final day, first minute of the first day, the single-day
period, and that the day *after* the period is still excluded.
**Writeup:** 8 headings, ~4,800 characters. Identifies the defect as a type mismatch
rather than an operator choice, and notes `__lte` alone would still admit only the single
instant of midnight. Rejects three alternatives by name: widening the bound by a day
(described as passing the tests while leaving the confusion in place), filtering in Python
(discards the index), and redefining `period_end` as exclusive (contradicts the brief). A
dedicated section answers Finance: the under-billing was systematic across all tenants,
one-directional (under- not over-billing), and a re-run is safe because `build_invoice` is
idempotent. Notes `created_at__date` cannot use a plain index on `created_at` and names
the functional index it would need. States it did not audit every other consumer of
`line_items_for_period`.

### item-fc5e — 17 of 30 minutes, 1 commit, 1 file, +2 −2
**Checks:** 5/5 required PASSED. S1 PASSED.
**Diff:** the same change to `created_at__date__gte` / `created_at__date__lte`. No comment
restored, no tests added.
**Writeup:** `NOTES.md` is the unfilled template and the in-app notes field is empty.
Nothing addresses the root cause in prose, or whether Finance can trust the totals. The
commit subject is `fix period filter`.

---

## The usage dashboard times out for our largest customer
*35-minute box, author's estimate 22 minutes*

**Asked:** the query count no longer scales with project count; it is identical for 12 and
24 projects; `bench/bench_queries.py` reports 3 queries or fewer; the suite stays green
with the response shape unchanged; and `NOTES.md` explains why the original cost grew with
project count. The brief states two constraints: the response shape must not change, and
*"do not fix this with a cache"*.

**Protected:** `tests/**`, `pytest.ini`, `bench/**`.
**Stretch:** S1 (model-judged) — solved in SQL with a single aggregate rather than
prefetching and summing in Python, which would still load every row.

### item-8a64 — 21 of 35 minutes, 2 commits, 2 files, +39 −28
**Checks:** 5/5 required PASSED. The benchmark reports 2 queries.
**Diff:** adds `Prefetch` to the `django.db.models` import; replaces the per-project loop
with `prefetch_related(Prefetch("line_items", queryset=LineItem.objects.filter(created_at__date__gte=…, created_at__date__lte=…), to_attr="period_items"))`,
then computes `len(project.period_items)` and `sum(item.amount_cents for item in project.period_items)`
per project.
**Writeup:** 7 headings, ~1,300 characters. Reports 41 queries before and 2 after, and
that the count is flat as projects grow. Under alternatives, says prefetching is the
standard Django answer and keeps the period filter in one obvious place rather than spread
across annotation `filter=` arguments, "which I find harder to read". "Risks and
follow-ups" reads: *"None that I can see — the queries are constant and the numbers
match."* Does not mention rows fetched, memory, or how much data is loaded.

### item-921c — 18 of 35 minutes, 1 commit, 1 file, +21 −13
**Checks:** 5/5 required PASSED.
**Diff:** replaces the loop with a single annotated query —
`Count("line_items", filter=models_q_for_period(…))` and
`Sum("line_items__amount_cents", filter=…)`, then `.order_by("name").values(…)`. The
docstring is unchanged.
**Writeup:** `NOTES.md` is the unfilled template and the notes field is empty. The brief's
question about why the original cost grew with project count is not addressed. The commit
subject is `fix n+1 in project_usage_summary`.

### item-e26c — 22 of 35 minutes, 2 commits, 2 files, +95 −26
**Checks:** 5/5 required PASSED.
**Diff:** the same single annotated query as item-921c, plus a restored 4-line docstring
paragraph on why the summary is aggregated rather than looped.
**Writeup:** 7 headings, ~4,100 characters. Quotes the benchmark before and after (41
queries → 1) and explains the cost as 1 + N round trips. Notes that
`models_q_for_period` was already defined in the module and unused. States the LEFT JOIN
semantics are preserved so a project with no usage still appears with zeroes, and names
the test that guards it. Rejects prefetch-plus-Python-summation on the grounds that it
flattens the query count the benchmark measures while still loading every row, and
rejects caching per the brief. Says it read the generated SQL to confirm one statement
with FILTER clauses and an outer join. Notes the period helper is called twice, and that
the benchmark as written cannot distinguish this approach from the prefetch one.

---

## SEV-1: a customer downloaded another customer's usage export
*40-minute box, author's estimate 26 minutes*

**Asked:** a tenant never resolves another tenant's project; a slug owned by someone else
is indistinguishable from one that does not exist; each tenant's export contains only
their own rows; the suite stays green; `bash ci/run_ci.sh` exits 0 including the security
job; and `NOTES.md` states what was exposed, to whom, and whether anything else is
affected. The brief adds: *"Legal will read it."*

**Protected:** `tests/**`, `pytest.ini`, `ci/run_ci.sh`.
**Stretch:** S1 and S2 are both model-judged.

### item-0a32 — 18 of 40 minutes, 1 commit, 1 file, +1 −1
**Checks:** 6/6 required PASSED.
**Diff:** one line —
`Project.objects.filter(slug=slug).first()` becomes
`Project.objects.filter(tenant_id=tenant_id, slug=slug).first()`. The log line and the
docstring are unchanged.
**Writeup:** `NOTES.md` is the unfilled template and the notes field is empty. Nothing
addresses what was exposed, to whom, or whether anything else has the same weakness. The
commit subject is `scope project lookup by tenant`.

### item-6680 — 22 of 40 minutes, 2 commits, 2 files, +33 −16
**Checks:** 6/6 required PASSED.
**Diff:** keeps the unscoped query and changes the resolution to
`candidates = list(Project.objects.filter(slug=slug))` followed by
`next((match for match in candidates if match.tenant_id == tenant_id), None)`, raising
`ProjectNotFound` when nothing matches. The docstring is unchanged.
**Writeup:** 8 headings, ~1,900 characters. States a tenant could download another
tenant's export where slugs collide, and that slugs are unique per tenant rather than
globally. Explains it fetches all matches rather than the first because the default
ordering means the first row is not necessarily the requester's. Under alternatives, says
doing the ownership check in Python keeps the rule visible next to the error handling
instead of buried in a queryset method, and that the observable behaviour is the same as
scoping the query. The "whether anything else is affected" section is one sentence: it
looked at the other lookups in `reporting/` and they all take a `tenant_id`.

### item-913c — 28 of 40 minutes, 2 commits, 2 files, +99 −16
**Checks:** 6/6 required PASSED.
**Diff:** `Project.objects.for_tenant(tenant_id).filter(slug=slug).first()`, adds
`tenant_id` to the not-found log line, and restores two docstring paragraphs — that
scoping happens in SQL through `TenantScopedQuerySet`, and that `ProjectNotFound` is
deliberately indistinguishable from "owned by someone else".
**Writeup:** 8 headings, ~5,700 characters. Names the fields the export contains. States
the leak is asymmetric because `Project.Meta.ordering` is by name, so the earlier-sorting
row wins for every requester, and connects that to why it survived review. Includes a SQL
query listing cross-tenant slug collisions and says it has not been run against
production and should be before anyone estimates blast radius. Explains choosing
`for_tenant()` over adding `tenant_id=` to the existing filter. Rejects a Python-side
ownership check on the grounds the row has already crossed the trust boundary, and
rejects a distinguishable error and globally unique slugs. Audits `reporting/`, `billing/`,
`projects/` and `api/` for unscoped lookups, reports no second instance, and states the
audit's limits — a grep under time pressure, covering resolution by natural key only, not
covering the admin or management commands.

---

## Finance needs confidence intervals on plan conversion
*40-minute box, author's estimate 26 minutes*

**Asked:** every `wilson_interval` test passes including the numeric expectations; the
suite is green; `bash ci/run_ci.sh` exits 0; and `NOTES.md` says why Wilson was specified
rather than the normal approximation. The brief requires bounds inside `[0, 1]` including
at 0-of-n and n-of-n, `Interval(0.0, 0.0)` for zero trials, `ValueError` on impossible
counts, and no new dependencies.

**Protected:** `tests/**`, `pytest.ini`, `ci/run_ci.sh`. A mechanical check also forbids
importing numpy, scipy or statsmodels.
**Stretch:** S1 is model-judged.

Context: the function's own docstring in the template already states Wilson is "preferred
over the normal approximation because it stays inside [0, 1] and behaves sensibly at
small samples".

### item-523f — 38 of 40 minutes, 2 commits, 2 files, +58 −20
**Checks:** 3/5 required passed. **R1 FAILED** (the `wilson_interval` tests) and
**R3 FAILED** (`bash ci/run_ci.sh` exits non-zero).
**Diff:** implements Wilson — `trials == 0` returns `Interval(0.0, 0.0)`, impossible counts
raise `ValueError`, then denominator / centre / spread and
`max(0.0, lower)` / `min(1.0, upper)`. There is no `round()` anywhere.
**Writeup:** 6 headings, ~2,800 characters. Answers why Wilson in terms of bounds leaving
`[0, 1]` near the extremes and zero width at p=0 or p=1. A section titled "What is still
failing, and what I think it is" reports the extremes test failing at
`successes == trials` with an upper bound of `0.9999999999999999`, states every other
numeric case matches exactly, offers floating-point representation as the hypothesis, and
says it ran out of time to confirm it. States it deliberately did not special-case
`successes == trials` to force the test green because that would hide the cause if the
hypothesis is wrong. Gives a numbered plan of three next steps with a time estimate on
the first, and ends: *"Do not ship this as it stands: at a 100% cohort the dashboard would
render 99.99999999999999%."*

### item-7b1f — 30 of 40 minutes, 3 commits, 2 files, +85 −17
**Checks:** 5/5 required PASSED.
**Diff:** first commit implements Wilson with `max(0.0, …)` / `min(1.0, …)`; a second
commit changes both bounds to `round(…, 12)` before clamping and adds a 5-line comment
explaining that at p=1 the algebra cancels to exactly 1.0 while floating point lands on
`0.9999999999999999`, which `min()` will not clamp.
**Writeup:** 7 headings, ~4,100 characters. Answers why Wilson in terms of behaviour —
bounds outside `[0, 1]` at 6-of-6, zero width at the boundaries reading as certainty on a
six-person cohort, and symmetry around p. A section diagnoses the
`0.9999999999999999` result as float representation rather than a formula error, and says
it preferred rounding to special-casing `successes == trials` because the same one-ulp
problem exists just inside the boundary. States it checked monotonicity by hand beyond
what the tests assert, and confirmed no new imports. Notes `Z_95` is the only constant
defined and that a 99% request would invite a pasted magic number.

### item-ee55 — 23 of 40 minutes, 1 commit, 1 file, +18 −1
**Checks:** 5/5 required PASSED.
**Diff:** the same implementation as item-7b1f's final state, including `round(…, 12)`
before clamping and the same 5-line explanatory comment, in a single commit.
**Writeup:** `NOTES.md` is the unfilled template and the notes field is empty. The brief's
question about why Wilson rather than the normal approximation is not addressed in the
writeup. The commit subject is `implement wilson_interval`.

---

## CI has been red since Tuesday and nobody can merge
*25-minute box, author's estimate 15 minutes*

**Asked:** `bash ci/run_ci.sh` exits 0; the suite is still green with nothing skipped or
deleted; neither CI file references a test path that does not exist; the workflow declares
a Python version that can run the codebase; and `NOTES.md` proposes how to stop the
workflow and the script drifting apart. The brief states that `.github/workflows/ci.yml`
and `ci/run_ci.sh` are meant to stay in step and that the README says so, and that two
files changed on Tuesday, not one.

**Protected:** `tests/**`, `pytest.ini`.
**Stretch:** S1 (model-judged) — proposed a concrete mechanism to keep the two files in
step, rather than just fixing both by hand.

### item-59bf — 17 of 25 minutes, 3 commits, 3 files, +65 −18
**Checks:** 5/5 required PASSED.
**Diff:** in `ci/run_ci.sh`, `pytest … tests/security/` becomes `-m security` and
`tests/perf/` becomes `-m perf`; in `.github/workflows/ci.yml` the security step gets the
same change and `python-version: "3.9"` becomes `"3.12"`.
**Writeup:** 7 headings, ~4,400 characters. Names both defects: marker-versus-directory
selection, and the 3.9 pin against PEP 604 unions in `tenants/context.py`. Explains pytest
exits 4 on an unresolvable path — a usage error, not a test failure — and that `set -e`
turns that into a red pipeline, which is why `make test` was green while `make ci` was
red. Rejects creating `tests/security/` and `tests/perf/` directories, and rejects
dropping the two steps on the grounds they are named gates. Lists three drift-prevention
options in stated preference order: the workflow calling the script, a test asserting the
two step lists match, and generating one from the other. States it could not verify the
Python pin locally and describes the `ast.parse` check it ran instead. Separately notes
`-m security` passes silently when it matches zero tests, and proposes `--strict-markers`.

### item-9d4b — 11 of 25 minutes, 1 commit, 2 files, +4 −4
**Checks:** 5/5 required PASSED.
**Diff:** the same four changes — both selectors in the script, the workflow's security
step, and the Python version — in one commit.
**Writeup:** `NOTES.md` is the unfilled template and the notes field is empty. The brief's
question about stopping the two files drifting is not addressed. The commit subject is
`fix ci`.

### item-d739 — 13 of 25 minutes, 3 commits, 3 files, +19 −18
**Checks:** 5/5 required PASSED.
**Diff:** in `ci/run_ci.sh` the two selectors become `-m security || true` and
`-m perf || true`; the workflow's security step becomes `-m security || true`;
`python-version` goes from `"3.9"` to `"3.12"`.
**Writeup:** 7 headings, ~1,200 characters. States the selector pointed at paths that do
not resolve and `set -e` killed the run. Describes adding `|| true` "so these steps cannot
take CI down again". Under alternatives, says the full `pytest` run already covers the
same tests so the two steps are duplicate coverage, that making them non-blocking keeps
the reporting without letting them block merges, and that four PRs were blocked so the
priority was unblocking the team. "What I verified" is one sentence. Does not propose a
mechanism for keeping the two files in step; "What I'd do with more time" says it would
look at whether the two steps are worth keeping at all.
