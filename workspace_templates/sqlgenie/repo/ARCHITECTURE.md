# Architecture

Why this service is shaped the way it is. Read this before changing anything under
`nl2sql/policy/` or `db/migrations/`.

## The model is not a security control

A question arrives in English. A recorded model turns it into SQL. That SQL is then
**rewritten** to constrain every read to the asking tenant, and only then executed.

The prompt does ask for tenant-scoped SQL, and asking is all it does. A model that
ignores the instruction, a question crafted to talk it out of the instruction, or a
future prompt change that makes a new SQL shape common — none of those weaken isolation,
because isolation is not the model's job. Anything that treats the generator's
cooperation as a defence has no defence.

## Two layers, and why the tests are split to match

| Layer | Where | What it stops |
|---|---|---|
| 1. Query rewrite | `nl2sql/policy/row_level_policy.py` | SQL that reads a scoped table without a tenant predicate |
| 2. Row-level security | `db/migrations/0005_row_level_security.sql` | Any row the connecting role should not see, whatever the SQL says |

Defence in depth is the right design and it is a menace to test, because an end-to-end
assertion passes if *either* layer works. A suite made only of end-to-end tests stays
green with the rewriter completely broken — and tells you so on the day somebody
disables RLS for an unrelated reason.

`tests/security/test_cross_tenant.py` is therefore split three ways: tests of the
rewriter with no database at all, tests of the database executing deliberately unscoped
SQL, and tests of the whole pipeline. A fix that repairs only one layer fails the group
belonging to the other.

## The rewrite walks scopes, not tables

A SQL statement is a tree of query scopes: the outer select, each CTE body, each derived
table, each branch of a set operation, each lateral. **Every one of them can reference a
base table independently.**

Scoping only the outermost scope produces a query that is syntactically valid, returns
plausible rows, and reads the whole table. `WITH t AS (SELECT * FROM orders) SELECT *
FROM t` is the canonical case: the outer scope's only source is `t`, which is not a
table, has no tenant column, and matches nothing in the catalog. A rewriter that
enumerates tables rather than scopes finds nothing to constrain and says so by doing
nothing.

`sqlglot.optimizer.scope.traverse_scope` enumerates every scope and resolves derived
sources away, so a CTE name is never mistaken for a table.

### The policy fails closed, and proves it

Three refusals rather than skips:

- A table the catalog does not know → refuse. `is_tenant_scoped` **raises** for an
  unknown table rather than returning `False`, because the caller is deciding whether to
  constrain a reference and the only safe answer for something unidentifiable is no.
- A table-valued function as a source → refuse. The policy cannot reason about what rows
  `generate_series(...)` returns.
- More than one statement → refuse, at parse time, before any scoping is attempted.

And one closing invariant: after the walk, **every tenant-scoped table the statement
reads must have received a predicate somewhere**, or the request dies. That check is what
makes the one legitimate `continue` in the loop safe — a `LATERAL` scope is not a
`SELECT` and cannot take a `WHERE`, so its sources are constrained by the enclosing
select instead. Without the invariant, that `continue` would be exactly the silent skip
this module exists to avoid.

### The tenant is bound, never interpolated

The rewrite emits `%(tenant_id)s` and the value travels as a query parameter. No part of
this service formats a tenant id into a string that becomes SQL, which is why there is no
escaping helper anywhere in the codebase — there is nothing to escape.

The same applies to the RLS session setting: `SET LOCAL` cannot take a bound parameter,
so `set_config('app.tenant_id', %s, true)` is used instead. Transaction-local, so it
cannot outlive the request on a pooled connection.

## Two roles, and the `FORCE` that makes RLS real

PostgreSQL **exempts a table's owner from its row-level security policies** unless the
table is declared `FORCE ROW LEVEL SECURITY`. A service that connects as the owner of the
tables it queries has RLS enabled and inert: the policies exist, `\d` lists them, and
they filter nothing.

So migrations run as the owner, the application runs as `sqlgenie_app`, and
`sqlgenie_app` owns nothing — *and* all four fact tables force RLS anyway. Two mechanisms
for one property, because the failure mode is invisible and the cost is one line per
table.

`sqlgenie_app` is also denied `api_keys` and `tenants` outright. The role that executes
model-generated SQL should not be able to read the credential table under any
circumstances, including ones nobody has thought of.

## The model is recorded, not called

Generations live in `fixtures/llm_cassettes/`, keyed by
`sha256(model | system | prompt)`. A miss is an error; there is no network fallback.

**What that buys:** determinism. The same question produces the same SQL on every
machine, forever, so a test can assert on the SQL and a security test can assert on what
that SQL did.

**What it costs:** nothing here tells you whether the model is good at text-to-SQL today.
That is the right trade — live model output cannot be scored anyway, and everything worth
testing in this service is downstream of generation.

**The consequence worth knowing before you edit anything:** the prompt embeds the schema
section rendered from the catalog. Rename a column, reorder a table, reword an
instruction, and every cassette key moves at once. `tests/test_cassettes.py` checks the
join between the transcript, the cassettes and the live prompt code, so that surfaces as
one clear failure naming `make cassettes` rather than as fifty confusing ones.

`fixtures/recordings.jsonl` and the cassettes are both committed, and the redundancy is
deliberate: the transcript is readable and diffable, so `git log -S "WITH" -- fixtures/`
tells you when generated SQL started using common table expressions and which commit
caused it. The cassettes are named by a hash nobody can read.

## Both tenants are identical on purpose

The seed data gives ACME and BORG the same customer names, the same SKUs, the same order
ids and the same totals. Only `tenant_id` differs.

A fixture where one tenant sells kayaks and the other sells industrial lubricant makes a
leak obvious at a glance — which means every test written against it accidentally passes
for the wrong reason, because the author saw sensible rows and moved on. Identical data
gives a leak exactly one signature: **the row count doubles**. Twenty orders becomes
forty, and nothing else changes.

## The audit trail

Three rules, each because the obvious alternative makes the trail useless exactly when
somebody needs it:

- **Log the SQL that ran, not the SQL that was generated.** They differ by the predicate,
  which is the entire subject of any incident here.
- **Log on the rejection path too.** A refused query is the most interesting event this
  service produces. A trail of successes describes a service where nobody has ever tried
  anything.
- **Log before returning rows.** Writing the record afterwards means a query that times
  out or returns ten million rows leaves no trace, which inverts the relationship between
  how alarming an event is and how likely it is to be recorded.

## What is deliberately not here

**No ORM.** Two roles with two very different privilege sets, and SQL that is generated
rather than written. An abstraction over that would hide the differences this design is
built around.

**No live LLM SDK.** See above.

**No tenant parameter on any endpoint.** The tenant comes from the API key and from
nowhere else — no header a client can set, no override for internal callers. Every one of
those is a feature somebody eventually asks for, and every one is the bug this service
exists not to have.

**No sample values in `/v1/schema`.** Table and column names only. Row counts, minimums
and example values are all things somebody will request to "help the model", and all of
them turn that endpoint into a way to read another tenant's data one statistic at a time.
