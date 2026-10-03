"""Exercises built on the ``sqlgenie`` base application.

Same ``(base_app, mutations)`` shape as the other catalog modules, and baselines are
likewise **measured** into ``baselines.json`` by the verification harness rather than
authored here.

What distinguishes this base app is that **every defect here is silent and every one is
a disclosure**. Nothing crashes, no total fails to reconcile, and the output of a broken
build is indistinguishable from the output of a working one -- the rows look right
because, with two tenants whose data is identical by design, they *are* right-looking.
What differs is who the rows belonged to.

That shapes the briefs. None of them can open with a traceback, so each opens with the
way such a thing is actually discovered: a customer noticing a number they should not be
able to see, a support engineer finding a question they did not ask, a key that should
have stopped working in February.

It also shapes the grading. The single most important signal across all six is whether
the candidate changed the **failure mode** rather than the symptom -- from silent-skip to
fail-closed, from "this shape is handled" to "any shape I cannot handle is refused".
A fix that adds a branch for the one construct in the ticket leaves the next one open,
and `grading_notes` say so in every entry.
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


#: The tests are the proof, so editing them is tampering. Four additions specific to this
#: base app: ``attack/prompts.jsonl`` because the adversarial corpus is the specification
#: of what must be refused, ``fixtures/**`` because the recordings and cassettes are what
#: make the exercise deterministic, ``bench/**`` because one exercise is graded on a
#: measurement it produces, and ``tools/**`` because regenerating either fixture set would
#: change every constant the suite asserts.
STANDARD_PROTECTED = [
    "tests/**",
    "pyproject.toml",
    "ci/run_ci.sh",
    ".github/workflows/ci.yml",
    "attack/prompts.jsonl",
    "fixtures/**",
    "bench/**",
    "tools/gen_seed_data.py",
    "tools/gen_cassettes.py",
    "db/seed.sql",
]

#: Shared context: why the model is not the boundary, and what the two layers are for.
TWO_LAYERS_EXCERPT = {
    "path": "ARCHITECTURE.md",
    "line_range": "17-33",
    "why": (
        "'Two layers, and why the tests are split to match'. States that an end-to-end "
        "assertion passes if either layer works, which is why the security suite is in "
        "three groups and why a fix to one layer does not turn the other group green."
    ),
}

#: Shared context: the fixture design that makes a leak visible at all.
IDENTICAL_TENANTS_EXCERPT = {
    "path": "ARCHITECTURE.md",
    "line_range": "118-128",
    "why": (
        "'Both tenants are identical on purpose'. Explains why a leak cannot be spotted "
        "by reading the rows and shows the one signature it does have: the row count "
        "doubles. Worth reading before trying to eyeball any output here."
    ),
}


# ---------------------------------------------------------------------------
# ex-036 -- ensure tenant isolation for text-to-SQL
# ---------------------------------------------------------------------------

EX036 = {
    "slug": "ex-036-a-cte-query-returned-every-tenants-orders",
    "exercise_number": 36,
    "title": "The tenant rewrite stopped constraining and nothing went wrong",
    "exercise_type": ExerciseType.TENANT_ISOLATION,
    "base_app": BaseApp.SQLGENIE,
    "difficulty": Difficulty.ADVANCED,
    "defect_class": "unscoped_query_via_unhandled_sql_node",
    "time_limit_minutes": 50,
    "expected_time_minutes": 32,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["security", "multi-tenant", "sql", "postgres", "row-level-security"],
    "brief_md": """\
## SEV-1 — the query rewriter has been emitting unscoped SQL

**Found by:** a security review, not by a customer
**Status:** confirmed. **No disclosure has occurred.**

Read that last line first, because it is the only good news and it is doing a lot of
work.

The tenant rewrite is supposed to constrain every read in a generated statement to the
asking tenant. For an unknown period it has been emitting SQL with no predicate at all on
several common query shapes — including the one behind this, which customers run monthly:

> Compare my monthly order totals to last year

Those queries ran. They returned the correct rows anyway, because row-level security in
the database refused to hand over anybody else's. **We have been relying on the backstop
without knowing it.**

The audit trail is also wrong, in a way that matters for working out how long this has
been true.

### What we know

- **It fires on an ordinary question.** No crafted input, no injection, no unusual API
  usage.
- `make test` is red. Read the failures as a group rather than one at a time — which
  groups fail, and which do not, is the finding.
- The adversarial corpus in `attack/prompts.jsonl` has eighteen cases with their expected
  outcomes. `make replay` runs them. Several that should be constrained are not.
- **One of the eighteen must be *allowed*.** A policy that refuses everything passes
  seventeen cases and is not a fix.

### Reproducing it

```bash
docker compose up -d --wait
make migrate && make seed
make test
make replay
```

`ARCHITECTURE.md` describes how isolation is supposed to work and how the test suite is
arranged to tell the two layers apart. Read it before changing anything — the shape of
the failures will tell you a lot once you know what each group proves.

### What we need

Isolation restored in the rewriter for **every** query shape, not for the one in the
ticket. Then a `NOTES.md` the security team can act on: what would have been exposed had
the second layer not held, how long this was true, and what the audit trail can and
cannot tell us about it. `git log` is available and the history is real.

### Watch out for

The question in the report is legitimate and so is the SQL it generates. Nothing here is
an attack. If your fix makes that report stop working, you have moved the problem rather
than solved it.
""",
    "definition_of_done": [
        "R1: the CTE policy test passes",
        "R2: all 18 adversarial cases behave as attack/prompts.jsonl declares",
        "R3: no statement runs with a scoped table left unconstrained",
        "R4: the refusal path is audited again",
        "R5: the whole suite is green, with no test skipped, deleted or weakened",
        "R6: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md says what would have been exposed, and for how long this was true",
    ],
    "focus_paths": [
        "src/sqlgenie/nl2sql/policy/row_level_policy.py",
        "src/sqlgenie/nl2sql/pipeline.py",
    ],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/security/test_cross_tenant.py::test_policy_scopes_a_cte_query",
            "weight": 4,
            "required": True,
            "description": "The predicate lands inside the CTE body, where the table is",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/security/test_cross_tenant.py::test_policy_handles_every_adversarial_shape"
            ),
            "weight": 5,
            "required": True,
            "description": "All 18 shapes, including the one that must be allowed through",
        },
        {
            "id": "R3",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/security/test_cross_tenant.py::"
                "test_policy_constrains_every_scoped_table_it_reads"
            ),
            "weight": 3,
            "required": True,
            "description": (
                "Across the whole corpus, no statement is scoped only partially -- the "
                "invariant that makes the traversal's coverage provable"
            ),
        },
        {
            "id": "R4",
            "kind": CheckKind.PYTEST,
            "target": "tests/security/test_cross_tenant.py::test_end_to_end_a_refusal_is_audited",
            "weight": 2,
            "required": True,
            "description": "The rejection path leaves a record, with the SQL that was refused",
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
            "description": "The CI pipeline passes, including the corpus replay",
        },
        {
            "id": "R7",
            "kind": CheckKind.FILE_UNCHANGED,
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, the adversarial corpus, the fixtures and the benchmark are untouched",
        },
        {
            "id": "R8",
            "kind": CheckKind.GREP_ABSENT,
            # Matches a tenant predicate built by interpolation -- an f-string brace,
            # a concatenation, or .format() -- and deliberately NOT `%(tenant_id)s`,
            # which is the correct psycopg binding and appears throughout the pristine
            # code and its docstrings.
            "target": r"""tenant_id['"]?\s*=\s*['"]?\s*(\{|\+)|\.format\([^)]*tenant""",
            "paths": ["src/sqlgenie/**/*.py"],
            "weight": 2,
            "required": True,
            "description": (
                "The tenant is never interpolated into SQL. A rewriter that formats it "
                "in has an injection vector of its own"
            ),
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 3,
            "required": False,
            "stretch": True,
            "description": (
                "Changed the failure mode, not just the shape coverage: a reference the "
                "policy cannot resolve now refuses rather than being skipped, so the next "
                "unhandled construct does not reopen the hole"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Recognised that row-level security is the only reason this was not a "
                "disclosure, and treated that as a near miss rather than as a reason the "
                "rewriter matters less"
            ),
        },
        {
            "id": "S3",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Bounded the exposure window using evidence: git log dates the change, "
                "and the audit trail cannot confirm it because refusals went unrecorded "
                "and the stored SQL was pre-rewrite -- which is itself the finding"
            ),
        },
    ],
    "baseline": baseline("ex-036-a-cte-query-returned-every-tenants-orders"),
    "context_excerpts": [
        TWO_LAYERS_EXCERPT,
        IDENTICAL_TENANTS_EXCERPT,
        {
            "path": "src/sqlgenie/nl2sql/policy/row_level_policy.py",
            "line_range": "1-21",
            "why": (
                "The module docstring, which states that the rewrite walks scopes rather "
                "than tables and why, and that the policy fails closed. The contract the "
                "fix has to restore, written where the code is."
            ),
        },
        {
            "path": "ARCHITECTURE.md",
            "line_range": "129-142",
            "why": (
                "'The audit trail' -- the three rules it follows, including that the SQL "
                "recorded must be the SQL that ran and that refusals are recorded. Two of "
                "the three are currently being broken."
            ),
        },
    ],
    "hints": [
        "Run `make test` and group the failures by file. Notice which group does *not* "
        "fail: the row-level-security tests are all green. `ARCHITECTURE.md` explains why "
        "the suite is split into layers and what it means that only some layers are red.",
        "`make replay` prints which adversarial shapes behave differently from what the "
        "corpus declares. Look at what they have in common: where in the statement does "
        "the base table actually appear in each of them?",
        "`enforce_tenant_scope` iterates over something that was narrowed. Compare what "
        "it walks now against what `collect_base_tables` just above it walks, and read "
        "what the module docstring says a scope is.",
    ],
    "grading_notes": """\
**Two defects, and the ticket names neither.**

**V1, primary** — `enforce_tenant_scope` iterates `list(traverse_scope(tree))[-1:]`, so
only the statement's outermost scope is visited. Every CTE body, derived table, set-
operation branch and subquery goes unconstrained; the fail-closed raise for an
unresolvable reference is downgraded to a silent skip, and the closing coverage invariant
is deleted so that nothing notices. The attached comment blames a double-scoped lateral
join, which is a real thing that can happen and is not the right response to it.

**V2, audit gap** — the refusal branch in `pipeline.ask` no longer records, and the
success record stores `generation.sql` rather than `scoped.sql`. So the trail shows what
the model proposed rather than what ran, and shows nothing at all for anything refused.

**The expected fix** restores the full `traverse_scope` walk, the fail-closed raise, the
coverage invariant, and both audit paths.

**Measured:** 23 tests fail. **The row-level-security group stays green**, and that is
the most important fact about this exercise. The database layer is intact and is the only
reason unscoped SQL returned correct rows. A candidate who notices which group did *not*
fail has understood both the incident and the point of the three-way split.

**What separates a strong answer.**

*S1 is the one that matters.* A fix that adds a `WITH` branch passes R1 and fails several
R2 cases. A fix that walks every scope passes both and is still only half the answer: the
question is what happens to a construct the walk encounters and cannot resolve. Restoring
the raise — and the end-of-walk assertion that every scoped table actually received a
predicate — is what makes the next unanticipated shape fail closed instead of silently
open. **Cap correctness at 65 for a fix that special-cases shapes, even with every test
green**, and say why: the defect class reopens the moment somebody writes SQL nobody
anticipated.

*S2* rewards reading the near miss correctly. Row-level security is why no data moved,
and there are two wrong conclusions available: that the rewriter therefore matters less,
and that the incident is minor. Both are wrong for the same reason — the service was one
misconfiguration away from a disclosure and had no way of knowing. A candidate who says
so, and ideally notes that nothing would have alerted them either, has drawn the lesson
the exercise is built around.

*S3* is the incident work. The brief asks how long this was true. `git log` dates both
changes. The audit trail cannot confirm it, because V2 stopped recording refusals and
stored the pre-rewrite SQL for everything else — so the one record that would show
whether unscoped statements ran is the record the same incident corrupted. A candidate
who reports *"I cannot bound this from the trail, and here is why"* has produced a better
answer than one who guesses a number.

**Watch for:**

- **Appending the predicate to the outer query only.** Passes R1 by accident on the
  single-CTE case and fails the two-level and set-operation cases. The outer scope's
  source is the CTE name, which has no tenant column.
- **Filtering rows in Python after execution.** Not a fix. The query still read every
  tenant's rows, they still crossed the trust boundary, and the database still did the
  work. If tests pass this way it is a symptom patch — set the flag.
- **Interpolating the tenant id** with an f-string instead of binding it. Caught by R8,
  and it replaces a disclosure bug with an injection bug.
- **Suppressing CTE generation in the prompt.** Treats the model as the security
  boundary, which `ARCHITECTURE.md` opens by rejecting. It also breaks the customer's
  report, which the brief explicitly warns against.
- **Refusing everything.** Passes seventeen of eighteen adversarial cases and fails a18,
  the legitimate cross-tenant question about shared reference data. That case exists
  precisely to catch this.
- **Editing the corpus or the tests.** Protected. Hard F.
""",
}


# ---------------------------------------------------------------------------
# ex-037 -- ensure tenant isolation for text-to-SQL
# ---------------------------------------------------------------------------

EX037 = {
    "slug": "ex-037-the-schema-endpoint-started-returning-data",
    "exercise_number": 37,
    "title": "The schema endpoint started answering questions nobody asked it",
    "exercise_type": ExerciseType.TENANT_ISOLATION,
    "base_app": BaseApp.SQLGENIE,
    "difficulty": Difficulty.ADVANCED,
    "defect_class": "schema_endpoint_leaks_other_tenants_values",
    "time_limit_minutes": 45,
    "expected_time_minutes": 28,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["security", "multi-tenant", "api-design", "data-exposure"],
    "brief_md": """\
## SEV-1 — customer data reachable without running a query

**Reported by:** our own security review, two days before a customer would have
**Status:** confirmed

`GET /v1/schema` describes the tables a caller may ask about. A reviewer noticed it was
also returning example values from those tables — and the examples were not filtered by
tenant.

Any customer with a valid API key could read other customers' data by calling an endpoint
that was never considered a data path. No question asked, no SQL generated, no tenant
predicate anywhere near it, and **no audit record**, because the audit trail only records
questions.

### What we know

- One test is failing and it names the problem.
- The change was made for a sensible reason, and the reason is in the diff. The feature
  it was trying to deliver is real; the implementation gave it away.
- `ARCHITECTURE.md` has a paragraph on this endpoint under "What is deliberately not
  here" — it was written before the change, and predicts it.

### Reproducing it

```bash
docker compose up -d --wait
make migrate && make seed
make test
curl -s -H "X-Api-Key: acme-dev-key" localhost:$WS_APP_PORT/v1/schema | jq
```

Both tenants are seeded with identical data, so look at the *shape* of the response
rather than trying to spot a foreign-looking value. `ARCHITECTURE.md` explains why the
fixtures are built that way.

### What we need

The endpoint returns what a caller needs to ask a question and nothing more. If you
believe the underlying request — helping the generator pick the right column — is worth
serving, say in `NOTES.md` how you would serve it safely. That is a design question and
we would rather have your answer than have you quietly decide there isn't one.
""",
    "definition_of_done": [
        "R1: tests/test_api.py::test_schema_exposes_no_data passes",
        "R2: the schema endpoint still lists every queryable table",
        "R3: the whole suite is green, with no test skipped, deleted or weakened",
        "R4: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md says how the original request could be served without exposing rows",
    ],
    "focus_paths": ["src/sqlgenie/api.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_api.py::test_schema_exposes_no_data",
            "weight": 5,
            "required": True,
            "description": "No seeded value appears in the schema response",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_api.py::test_schema_lists_tables_and_columns",
            "weight": 3,
            "required": True,
            "description": "The endpoint still does its actual job",
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
            "description": "Tests, the corpus, the fixtures and the benchmark are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 3,
            "required": False,
            "stretch": True,
            "description": (
                "Engaged with the underlying request rather than only deleting the code: "
                "proposed something concrete -- enumerated values held in the catalog, a "
                "tenant-scoped sample behind the normal query path, or a documented "
                "refusal -- instead of silently dropping the feature"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Noticed that this path produced no audit record at all, so the exposure "
                "cannot be bounded from the trail, and said so"
            ),
        },
    ],
    "baseline": baseline("ex-037-the-schema-endpoint-started-returning-data"),
    "context_excerpts": [
        IDENTICAL_TENANTS_EXCERPT,
        {
            "path": "ARCHITECTURE.md",
            "line_range": "143-160",
            "why": (
                "'What is deliberately not here', including the paragraph on why this "
                "endpoint returns names only. Written before the change that broke it, "
                "and it describes the failure almost exactly."
            ),
        },
        {
            "path": "src/sqlgenie/api.py",
            "line_range": "100-130",
            "why": (
                "The endpoint itself, alongside /v1/ask, so the contrast is visible: one "
                "of these resolves a tenant and scopes a query, and the other does not."
            ),
        },
    ],
    "hints": [
        "Run `make test`. One test fails, and its docstring says what the endpoint is "
        "and is not allowed to return.",
        "Call the endpoint and read the response. Then ask which of the fields in it "
        "required a database query to produce — and what scoped that query.",
        "`git log -p src/sqlgenie/api.py` shows the change and the reason given for it. "
        "The reason is legitimate; look at what the implementation had to reach for in "
        "order to satisfy it.",
    ],
    "grading_notes": """\
**Root cause.** `get_schema` in `src/sqlgenie/api.py` queries the database for distinct
values from each table's first name-like column and returns them as `samples`. The query
runs on the **owner** connection — the one used for migrations and key lookup — so it is
subject to no row-level security, and it carries no tenant predicate because it never
went through the policy.

**The expected fix** removes the sampling and returns names only. One test fails and it
is precise about what must not appear.

**Why this is advanced despite being a small diff.** The fix is easy. What is being tested
is whether the candidate recognises a *data path that does not look like one*. There is no
SQL generation here, no policy, no audit record, and nothing in the request that mentions
a tenant — which is exactly why it was missed in review and why `ARCHITECTURE.md` named it
in advance.

**S1 is where the marks are.** The motivating request — the generator guessing category
names wrongly — is real and does not disappear when the code is deleted. Good answers
include: putting an enumerated list of allowed values in the catalog as static data, since
categories are not tenant data; serving samples through the normal `/v1/ask` path so they
are scoped and audited like everything else; or stating plainly that the request cannot be
served safely and why. Any of those is a complete answer. Silently deleting the feature
and saying nothing is a fix that will be re-broken by whoever asked for it originally.

**S2** rewards noticing the absence of evidence. This endpoint writes no audit record, so
there is no way to tell who called it or what came back. A candidate who reports that the
blast radius is unbounded *because the path was not instrumented* has understood the real
problem better than one who asserts a number.

**Watch for:**

- **Scoping the sample query instead of removing it.** Adding `WHERE tenant_id = ...`
  makes the test pass and keeps a second, parallel data path that bypasses the policy, the
  audit trail and the row ceiling. Accept it as correct-but-worse and say so; if they did
  not notice they had built a second query path, mark engineering quality down.
- **Filtering the response after fetching.** The rows still left the database on an
  unscoped connection. Symptom patch — set the flag.
- **Removing the endpoint entirely.** Breaks R2, and the endpoint has a legitimate job.
- **Editing the test to allow samples.** Protected. Hard F.
""",
}


# ---------------------------------------------------------------------------
# ex-038 -- ensure tenant isolation for text-to-SQL
# ---------------------------------------------------------------------------

EX038 = {
    "slug": "ex-038-the-dashboard-cache-crossed-a-tenant-boundary",
    "exercise_number": 38,
    "title": "Two tenants, one cache, and the wrong numbers on a dashboard",
    "exercise_type": ExerciseType.TENANT_ISOLATION,
    "base_app": BaseApp.SQLGENIE,
    "difficulty": Difficulty.ADVANCED,
    "defect_class": "response_cache_key_omits_tenant",
    "time_limit_minutes": 45,
    "expected_time_minutes": 28,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["security", "multi-tenant", "caching", "concurrency"],
    "brief_md": """\
## SEV-1 — one customer's dashboard served another customer's rows

**Reported by:** support, after two customers reported the same numbers
**Status:** confirmed, intermittent

Two customers on the same dashboard panel reported figures that matched each other
exactly. They have no relationship and their accounts are unrelated.

It is intermittent in the way that matters: **whoever asks first gets the right answer**,
and everybody after them gets that answer too. Restarting the service makes it go away
until the first request arrives.

### What we know

- Two tests are failing. Both ask the same question as two different tenants.
- The change responsible was a performance fix and the reasoning behind it is sound —
  the dashboard does re-ask the same handful of questions on every refresh, and that was
  genuinely the bulk of our database load.
- The tenant predicate is still being applied. Row-level security is still on. **Both
  layers of isolation are working.** The rows are correctly scoped for the tenant that
  caused them to be fetched.

### Reproducing it

```bash
docker compose up -d --wait
make migrate && make seed
make test
```

Then, with the stack up, ask the same question as each tenant in turn and compare:

```bash
docker compose exec -T app sqlgenie ask --tenant acme "Show me my ten most recent orders"
docker compose exec -T app sqlgenie ask --tenant borg "Show me my ten most recent orders"
```

Both tenants hold identical data, so the values will look the same either way. One column
tells you whose rows you are actually looking at.

### What we need

The performance work kept, and correct. Deleting the cache fixes the bug and reintroduces
the load problem it was added for; if that is your decision, defend it in `NOTES.md` with
what you would do instead.
""",
    "definition_of_done": [
        "R1: tests/test_api.py::test_each_tenant_gets_its_own_rows passes",
        "R2: the reversed-order test passes too",
        "R3: the whole suite is green, with no test skipped, deleted or weakened",
        "R4: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md says whether the caching was kept and why",
    ],
    "focus_paths": ["src/sqlgenie/nl2sql/pipeline.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_api.py::test_each_tenant_gets_its_own_rows",
            "weight": 5,
            "required": True,
            "description": "Each tenant sees its own tenant_id in the returned rows",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_api.py::test_asking_twice_in_the_other_order_still_scopes",
            "weight": 3,
            "required": True,
            "description": "Neither tenant's position in the sequence is the lucky one",
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
            "description": "Tests, the corpus, the fixtures and the benchmark are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 3,
            "required": False,
            "stretch": True,
            "description": (
                "Kept the caching and made it correct by including the tenant in the key, "
                "rather than deleting the optimisation and leaving the load problem it "
                "was added to solve"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Observed that both isolation layers were working correctly and the leak "
                "happened upstream of them -- so a cache sitting above a security boundary "
                "has to carry every input that boundary depends on"
            ),
        },
        {
            "id": "S3",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Addressed unboundedness or invalidation: the cache has no eviction and no "
                "expiry, so it is also a memory leak and will serve stale answers after "
                "the underlying data changes"
            ),
        },
    ],
    "baseline": baseline("ex-038-the-dashboard-cache-crossed-a-tenant-boundary"),
    "context_excerpts": [
        IDENTICAL_TENANTS_EXCERPT,
        TWO_LAYERS_EXCERPT,
        {
            "path": "src/sqlgenie/nl2sql/pipeline.py",
            "line_range": "97-130",
            "why": (
                "The pipeline's entry point, where the tenant arrives as an explicit "
                "argument and is threaded into the scope, the execution and the audit "
                "record. Everything below this line is tenant-aware."
            ),
        },
    ],
    "hints": [
        "Run `make test`. Two tests fail; both ask one question as two tenants. Read "
        "what they compare — it is not the values, because both tenants hold the same "
        "ones.",
        "Ask the same question as `acme` and then as `borg` using `sqlgenie ask`. Then "
        "restart the stack and ask in the opposite order. The answer that changes tells "
        "you where the state lives.",
        "Something in `pipeline.ask` returns before the tenant is used. Find what it is "
        "keyed on, and compare that against the arguments `ask` needs in order to "
        "produce a correct answer.",
    ],
    "grading_notes": """\
**Root cause.** `pipeline.ask` memoises answers in a module-level dict keyed on the
question text alone. The tenant is an argument to `ask` and is not part of the key, so the
first caller's answer is returned to every subsequent caller asking the same question.

**The expected fix** includes the tenant in the key — `(tenant_id, question)` — or removes
the cache. The first is better and S1 rewards it.

**Why this is advanced.** Both isolation layers are working perfectly. The tenant predicate
is applied, row-level security is on and FORCEd, and the SQL that ran was correctly scoped
*for the tenant who triggered the fetch*. Every security test that inspects the rewrite or
the database passes. The leak is entirely above the boundary, in a layer nobody thinks of
as security-relevant — which is the transferable lesson and what S2 is for: **a cache in
front of a security boundary must key on everything that boundary depends on.**

It is also why the fixtures matter here. With two tenants holding identical data, the
returned *values* are correct either way. Only `tenant_id` distinguishes them, which is why
one benign recording selects it and why both failing tests use that question.

**Measured:** 2 tests fail, both in `tests/test_api.py`.

**S3 is the detail a senior engineer notices unprompted.** The cache has no size limit and
no expiry. Fixing only the key leaves a dict that grows without bound across every distinct
question every tenant ever asks, and that will serve a stale answer the moment an order is
placed. A candidate who mentions either — ideally with a concrete suggestion, a bounded LRU
or a short TTL — is doing the job properly.

**Watch for:**

- **Clearing the cache per request.** Makes the tests pass and removes the entire benefit.
  Correct but pointless; say so.
- **Keying on the question plus the API key** rather than the tenant. Works, but means two
  keys belonging to the same tenant get separate entries — harmless, slightly wasteful, and
  worth a note that the tenant is the real boundary.
- **Moving the cache below the tenant scope** so it stores scoped SQL rather than answers.
  A genuinely good alternative: the generation is the expensive, tenant-independent part.
  Credit it highly if they explain the reasoning.
- **Keying on the generated SQL.** Subtle and wrong in a specific way worth catching: the
  SQL is identical across tenants before rewriting, so this is the same bug with extra
  steps. If tests pass this way, check whether they keyed on pre- or post-rewrite SQL —
  post-rewrite still contains only a bound parameter, not the value.
""",
}


# ---------------------------------------------------------------------------
# ex-039 -- ensure tenant isolation for text-to-SQL
# ---------------------------------------------------------------------------

EX039 = {
    "slug": "ex-039-the-audit-trail-shows-every-tenants-questions",
    "exercise_number": 39,
    "title": "Support can read what every customer has been asking",
    "exercise_type": ExerciseType.TENANT_ISOLATION,
    "base_app": BaseApp.SQLGENIE,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "audit_trail_not_scoped_to_its_tenant",
    "time_limit_minutes": 30,
    "expected_time_minutes": 18,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["security", "multi-tenant", "audit", "api-design"],
    "brief_md": """\
## SEC-118 — the audit endpoint is not scoped

**Reported by:** an engineer, during an unrelated review
**Severity:** SEV-2

`GET /v1/audit` returns the recent questions and executed SQL for the calling tenant.
It is currently returning them for **every** tenant.

Any customer with a valid key can read what every other customer has been asking. The
questions people ask an analytics tool are a fairly precise description of what their
business is worried about this quarter, and the records include the SQL that ran.

### What we know

- One test is failing and it names the endpoint.
- The change has a reason attached, and the reason is a real one — support genuinely did
  need a way to see the whole trail while debugging a customer issue.
- The query path itself is fine. Nothing about the tenant rewrite or row-level security
  is involved here.

### Reproducing it

```bash
docker compose up -d --wait
make migrate && make seed
make test
```

### What we need

The endpoint scoped to its caller. Support's need does not go away because we closed this,
so say in `NOTES.md` how you would meet it — that is the part we actually want your
judgement on.
""",
    "definition_of_done": [
        "R1: tests/test_api.py::test_the_audit_trail_is_scoped_to_its_tenant passes",
        "R2: the whole suite is green, with no test skipped, deleted or weakened",
        "R3: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md proposes how support's need could be met safely",
    ],
    "focus_paths": ["src/sqlgenie/api.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_api.py::test_the_audit_trail_is_scoped_to_its_tenant",
            "weight": 5,
            "required": True,
            "description": "Each caller sees only its own records",
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
            "paths": [*STANDARD_PROTECTED],
            "weight": 0,
            "required": True,
            "description": "Tests, the corpus, the fixtures and the benchmark are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 3,
            "required": False,
            "stretch": True,
            "description": (
                "Proposed a concrete way to serve support's actual need -- a separate "
                "internal path, an explicit operator role, or an out-of-band tool -- "
                "rather than only closing the hole and leaving the request unanswered"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Articulated that an audit trail in a multi-tenant service is itself "
                "tenant data, and that reading it required no query and left no record"
            ),
        },
    ],
    "baseline": baseline("ex-039-the-audit-trail-shows-every-tenants-questions"),
    "context_excerpts": [
        {
            "path": "src/sqlgenie/api.py",
            "line_range": "148-170",
            "why": (
                "The endpoint, whose own docstring states the rule it is breaking. Worth "
                "reading as an example of a comment that outlived the behaviour it "
                "described."
            ),
        },
        {
            "path": "ARCHITECTURE.md",
            "line_range": "129-142",
            "why": (
                "'The audit trail' -- what it records and why, including that refusals are "
                "recorded. Context for what exactly is being exposed."
            ),
        },
    ],
    "hints": [
        "Run `make test`. One test fails and it is named after the endpoint.",
        "Read the handler's docstring, then read the line below it. They disagree.",
        "`audit.records()` takes an optional filter. Look at what the handler passes.",
    ],
    "grading_notes": """\
**Root cause.** `get_audit` in `src/sqlgenie/api.py` calls `audit.records()` with no
`tenant_id`, returning every tenant's records to any authenticated caller. One line, and
the handler's own docstring directly above it still describes the correct behaviour.

**The expected fix** restores `audit.records(tenant_id=tenant_id)`.

**Why intermediate rather than beginner.** The fix is trivial and the test points straight
at it, so the time box is short. What lifts it above beginner is that nothing in the system
flags this as a data path: no SQL is generated, no policy runs, no row-level security
applies, and — the detail worth drawing out — **reading the whole trail leaves no trace in
the trail**. A candidate who only changes the line has done the ticket. The marks are in
noticing what kind of data this was.

**S1 is the judgement.** Support's need was real. Good answers: a separate internal
endpoint behind an operator credential rather than a customer API key; shipping the trail
to a log pipeline where access is controlled and audited independently; or a CLI run by
staff with its own authentication. Any concrete proposal counts. A candidate who closes the
hole and says nothing about the original request has set up the next person to reopen it,
which is exactly how this one was introduced.

**Watch for:**

- **Filtering in the template or the client.** The records still left the service.
  Symptom patch — set the flag.
- **Adding an "internal" bypass flag** on the same endpoint, driven by a query parameter
  or header. That is the same bug with a password on it: anything a client can set, a
  client will set. If they do this, correctness is satisfied but engineering quality is
  not, and the feedback should say why.
- **Removing the endpoint.** Passes R1 by making the feature disappear. It has a
  legitimate purpose; note that.
""",
}


# ---------------------------------------------------------------------------
# ex-040 -- fix a critical bug fast
# ---------------------------------------------------------------------------

EX040 = {
    "slug": "ex-040-a-rotated-key-still-opens-the-door",
    "exercise_number": 40,
    "title": "A key we rotated out in February still works",
    "exercise_type": ExerciseType.CRITICAL_BUG,
    "base_app": BaseApp.SQLGENIE,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "revoked_key_still_authenticates",
    "time_limit_minutes": 25,
    "expected_time_minutes": 15,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["security", "authentication", "incident", "postgres"],
    "brief_md": """\
## INC-3302 — revocation does not revoke

**Severity:** SEV-1, ongoing
**Reported by:** a customer, who rotated a key after an employee left

A customer rotated an API key in February when an employee left. They tested the old key
this morning, expecting a rejection. It worked.

Every key we have ever issued still authenticates, including every key any customer has
ever revoked, for whatever reason they revoked it.

### What we know

- Keys are not deleted on revocation. The row stays, with `revoked_at` set — deleting it
  would destroy the record of which key did what, which we need precisely for incidents
  like this one.
- So revocation is a column that has to be **checked**.
- Two tests are failing.

### Reproducing it

```bash
docker compose up -d --wait
make migrate && make seed
make test
```

The seeded data includes one deliberately revoked key, `acme-retired-key`.

### What we need

Fix it first — this is live. Then `NOTES.md`: how long this has been true, what a customer
should be told, and whether we can tell from our own records which revoked keys were
actually used.
""",
    "definition_of_done": [
        "R1: tests/test_api.py::test_a_revoked_key_is_rejected passes",
        "R2: unknown and revoked keys are still indistinguishable to the caller",
        "R3: the whole suite is green, with no test skipped, deleted or weakened",
        "R4: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md says how long this was true and what customers should be told",
    ],
    "focus_paths": ["src/sqlgenie/tenancy/auth.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_api.py::test_a_revoked_key_is_rejected",
            "weight": 5,
            "required": True,
            "description": "A key with revoked_at set is refused",
        },
        {
            "id": "R2",
            "kind": CheckKind.PYTEST,
            "target": "tests/test_api.py::test_rejection_does_not_say_why",
            "weight": 3,
            "required": True,
            "description": (
                "Unknown and revoked return the same message, so the endpoint is not an "
                "oracle for which keys once existed"
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
            "description": "Tests, the corpus, the fixtures and the benchmark are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Kept unknown and revoked indistinguishable in the response while fixing "
                "the check, and explained that distinguishing them confirms which keys "
                "once existed"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Did the incident work: dated the regression from git log, and said "
                "whether the audit trail can show which revoked keys were actually used "
                "-- it records the tenant but not the key, so it cannot"
            ),
        },
    ],
    "baseline": baseline("ex-040-a-rotated-key-still-opens-the-door"),
    "context_excerpts": [
        {
            "path": "src/sqlgenie/tenancy/auth.py",
            "line_range": "1-35",
            "why": (
                "The module docstring, including why one exception type covers missing, "
                "unknown and revoked -- the reasoning the fix must not undo while making "
                "revocation work."
            ),
        },
    ],
    "hints": [
        "Run `make test`. Two tests fail in `tests/test_api.py`, and one of them uses a "
        "key the seed data marks as revoked.",
        "`resolve_tenant` in `src/sqlgenie/tenancy/auth.py` selects two columns from "
        "`api_keys`. Look at what it does with the second one.",
        "The fix must keep unknown and revoked producing the same error. The second "
        "failing test is there to stop a fix that makes the two distinguishable.",
    ],
    "grading_notes": """\
**Root cause.** `resolve_tenant` in `src/sqlgenie/tenancy/auth.py` selects `revoked_at`
and then tests only `if row is None`. The revocation column is fetched and ignored.

**The expected fix** restores `if row is None or row["revoked_at"] is not None`.

**Why the second test exists.** The obvious fix is one condition. A plausible variant
raises a *different* message for revoked keys — "this key was revoked" — which is friendlier
and turns the endpoint into an oracle: an attacker can now learn which keys this service
once issued, one guess at a time. `test_rejection_does_not_say_why` fails for that variant,
and S1 rewards a candidate who explains the reasoning rather than merely passing it.

**Measured:** 2 tests fail, both in `tests/test_api.py`.

**S2 is the incident work, and it has a real answer.** `git log` dates the change. The more
interesting half is whether we can tell which revoked keys were *used*: the audit record
holds `tenant_id` but not the key, so **it cannot**. A candidate who checks and reports
that limitation has done better than one who claims a number. If they propose recording a
key identifier in the audit record going forward, that is a genuine improvement — note that
it must be an identifier, not the key.

**Watch for:**

- **Filtering in SQL by adding `AND revoked_at IS NULL`.** Equally correct and arguably
  better — the database does the work and the application cannot forget. Accept it fully.
  If they do this, check they did not also drop `revoked_at` from the projection in a way
  that makes a future check impossible.
- **Deleting revoked rows instead.** Fixes authentication and destroys the record the
  brief explicitly says is needed. Mark it down and explain.
- **Returning a distinct error for revoked keys.** Caught by R2. Friendlier and worse.
- **Caching the lookup** without accounting for revocation. A revoked key would keep
  working until the cache expired, which is the same bug with a timer. Nothing in the suite
  catches this because there is no cache today; if a candidate adds one, raise it.
""",
}


# ---------------------------------------------------------------------------
# ex-041 -- fix a severe latency issue
# ---------------------------------------------------------------------------

EX041 = {
    "slug": "ex-041-every-question-pays-for-a-schema-check",
    "exercise_number": 41,
    "title": "Every question now waits on five lookups before it starts",
    "exercise_type": ExerciseType.LATENCY,
    "base_app": BaseApp.SQLGENIE,
    "difficulty": Difficulty.INTERMEDIATE,
    "defect_class": "catalog_metadata_refetched_per_request",
    "time_limit_minutes": 40,
    "expected_time_minutes": 24,
    "databases": [Database.POSTGRES],
    "needs_docker": True,
    "tags": ["latency", "postgres", "performance", "profiling"],
    "brief_md": """\
## PERF-410 — response times doubled and nobody changed a query

**Severity:** SEV-2
**Reported by:** the dashboard team

Median response time for `/v1/ask` roughly doubled last week. No query got slower, no
index changed, and the data has not grown meaningfully. Under load it is worse than
doubled, and the database is reporting far more statements per second than our request
rate accounts for.

### What we know

- **The answers are correct.** Same rows, same SQL, same tenant scoping. This is purely a
  cost problem.
- One test is failing, and it is not a correctness test — it counts.
- `bench/bench_ask.py` reports what answering one question costs in work rather than in
  milliseconds. A healthy run makes **3 statements** on the request connection and **0**
  schema lookups.
- The change responsible was defensive and was added for a good reason: a column rename
  had shipped without the catalog being updated, and the generator spent a day producing
  SQL for a column that no longer existed.

### Reproducing it

```bash
docker compose up -d --wait
make migrate && make seed
make test
make bench
```

Read the benchmark's output, not just its exit code.

### What we need

The cost back to a fixed number of statements per question, with `make bench` reporting
`catalog_queries` of 0.

The problem the change was solving is real. If you remove it, `NOTES.md` should say how a
catalog that has drifted from the schema would be caught instead — there is more than one
reasonable answer and we want yours.

### Watch out for

A per-request cost that scales with the number of tables rather than with traffic is the
kind of thing that looks fine in development and falls over at load. The benchmark
measures statements rather than time for the same reason.
""",
    "definition_of_done": [
        "R1: the request-path round-trip test passes",
        "R2: make bench reports catalog_queries of 0",
        "R3: the whole suite is green, with no test skipped, deleted or weakened",
        "R4: bash ci/run_ci.sh exits 0",
        "llm: NOTES.md says how catalog drift should be detected instead",
    ],
    "focus_paths": ["src/sqlgenie/nl2sql/pipeline.py"],
    "protected_paths": [*STANDARD_PROTECTED],
    "mutations": [{"op": "apply_patch", "patch": "mutation.patch"}],
    "checks": [
        {
            "id": "R1",
            "kind": CheckKind.PYTEST,
            "target": (
                "tests/test_catalog.py::test_answering_a_question_makes_a_fixed_number_of_round_trips"
            ),
            "weight": 4,
            "required": True,
            "description": "Three statements on the request connection, none of them schema probes",
        },
        {
            "id": "R2",
            "kind": CheckKind.BENCHMARK,
            "target": "python bench/bench_ask.py --json",
            "expect": {"metric": "catalog_queries", "op": "<=", "threshold": 0},
            "weight": 4,
            "required": True,
            "description": "No schema lookups on the request path; 5 per question when broken",
        },
        {
            "id": "R3",
            "kind": CheckKind.BENCHMARK,
            "target": "python bench/bench_ask.py --json",
            "expect": {"metric": "db_round_trips", "op": "<=", "threshold": 4},
            "weight": 2,
            "required": True,
            "description": "The statement count stays fixed rather than scaling with the catalog",
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
            "description": "Tests, the corpus, the fixtures and the benchmark are untouched",
        },
        {
            "id": "S1",
            "kind": CheckKind.LLM,
            "weight": 3,
            "required": False,
            "stretch": True,
            "description": (
                "Proposed a concrete alternative for catching catalog drift -- a CI check, "
                "a migration-time assertion, a start-up check -- rather than deleting the "
                "guard and leaving the problem it was added for unsolved"
            ),
        },
        {
            "id": "S2",
            "kind": CheckKind.LLM,
            "weight": 2,
            "required": False,
            "stretch": True,
            "description": (
                "Explained why a per-request cost proportional to the number of tables is "
                "worse than it looks: it is invisible in development and degrades with "
                "schema size rather than with traffic"
            ),
        },
    ],
    "baseline": baseline("ex-041-every-question-pays-for-a-schema-check"),
    "context_excerpts": [
        {
            "path": "bench/bench_ask.py",
            "line_range": "1-30",
            "why": (
                "What the benchmark measures and why it counts statements rather than "
                "timing them. Names the floor of three and says what each one is for."
            ),
        },
        {
            "path": "src/sqlgenie/nl2sql/catalog.py",
            "line_range": "1-20",
            "why": (
                "The catalog's module docstring: it is static data and the trust boundary "
                "for what may be queried. Relevant to where a drift check belongs."
            ),
        },
    ],
    "hints": [
        "`make bench` prints statements and schema lookups side by side. Compare them "
        "against the floor of three the benchmark's docstring describes.",
        "The failing test counts the statements issued on the connection the pipeline is "
        "given. Read what it asserts and what it prints when it fails.",
        "Something runs in `pipeline.ask` before the policy does, once per table in the "
        "catalog. Ask whether its result is ever used, and whether the request path is "
        "the right place for it.",
    ],
    "grading_notes": """\
**Root cause.** `pipeline.ask` runs a drift check before scoping: for each table in the
catalog it queries `information_schema.columns` on the request connection. Five tables, so
five extra statements per question, and the result is fetched and discarded.

**The expected fix** removes the check from the request path. Where it should go instead is
the interesting part and S1 is for that.

**Measured:**

| | statements on the request connection | catalog lookups |
|---|---|---|
| fixed | 3 | 0 |
| broken | 8 | 5 |

The three legitimate statements are the statement timeout, the tenant setting, and the
query itself.

**S1 is the whole exercise.** The guard was added for a real incident — a column rename
shipped without the catalog being updated. Deleting it and saying nothing recreates the
conditions for that incident. Good answers put the check somewhere it runs once rather than
per request: a CI step comparing the catalog against a freshly migrated database, an
assertion in the migration runner, a start-up check, or a test. Any of those is complete.

**S2 rewards understanding the shape of the cost.** Five extra statements is invisible on a
laptop with five tables and a local database. It scales with the size of the catalog, not
with traffic, so it gets worse as the product grows rather than as usage grows — and it is
paid before any useful work begins, so it inflates every request including the ones that
end in a refusal.

**Watch for:**

- **Caching the drift check's result** in a module-level flag. Passes both benchmarks and
  keeps the check. Reasonable, but note that it now runs once per process on a random
  request — the first one, which pays for everybody — and that a start-up or CI check is
  the same idea done deliberately.
- **Moving the check onto its own connection.** Makes the benchmark's numbers look right
  while leaving the cost in place: the statements still happen, they are just not counted.
  R1 would still fail, since it counts statements on the pipeline's connection — but if a
  candidate manages to satisfy both and the work is still per-request, that is a symptom
  patch. Set the flag.
- **Lowering what the benchmark measures.** `bench/**` is protected. Hard F.
- **Removing the check with no comment in NOTES.md.** Passes everything, earns no stretch,
  and is worth saying plainly in the feedback: the ticket told them the problem was real.
""",
}


#: Every sqlgenie exercise, in catalog order.
EXERCISES: list[dict] = [EX036, EX037, EX038, EX039, EX040, EX041]
