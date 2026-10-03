"""Tenant isolation, asserted at each of the three layers independently.

**Why three groups of tests rather than one end-to-end group.** This service defends
tenant isolation twice: the query rewriter constrains the SQL, and row-level security
constrains what the database will return regardless. Defence in depth is the right
design and it is a menace to test, because an end-to-end assertion passes if *either*
layer works. A suite made only of end-to-end tests would stay green with the rewriter
completely broken, and would tell you so on the day somebody disabled RLS for an
unrelated reason.

So:

``test_policy_*``
    The rewriter alone, as a pure function from SQL to SQL. No database. These fail if
    the rewrite stops constraining a shape, whatever the database would have done.

``test_rls_*``
    The database alone, executing deliberately unscoped SQL. These fail if row-level
    security is enabled but inert -- which is what happens when the application connects
    as the table owner and ``FORCE`` was never applied.

``test_end_to_end_*``
    Both together, through the real pipeline, which is what a user actually gets.

The seeded tenants are **identical in content** -- same names, same SKUs, same order ids,
same totals -- so a leak cannot be mistaken for plausible data. It shows up as a doubled
row count and nothing else.
"""

from __future__ import annotations

import json

import pytest

from sqlgenie.nl2sql import audit, catalog
from sqlgenie.nl2sql.audit import Outcome
from sqlgenie.nl2sql.policy.row_level_policy import PolicyError, enforce_tenant_scope
from tests.conftest import TENANT_A, TENANT_B, recording_by_id

pytestmark = pytest.mark.security

#: Orders seeded per tenant. A query that returns forty has read both tenants.
ORDERS_PER_TENANT = 20


def _attack_ids() -> list[str]:
    with open("attack/prompts.jsonl", encoding="utf-8") as handle:
        return [json.loads(line)["id"] for line in handle if line.strip()]


# ---------------------------------------------------------------------------
# Layer 1: the rewriter, with no database involved
# ---------------------------------------------------------------------------


def test_policy_scopes_a_cte_query(recordings) -> None:
    """**The marquee case.**

    ``WITH t AS (SELECT * FROM orders) SELECT * FROM t`` reads ``orders`` from inside the
    CTE body. The predicate therefore has to land inside the CTE, not on the outer
    select -- scoping the outer select constrains ``t``, which is not a table and has no
    tenant column, and leaves the actual read unconstrained.

    This is asserted on the SQL text rather than on returned rows on purpose. Row-level
    security would mask a failure here, and the point of this test is that the rewriter
    works on its own.
    """
    row = recording_by_id(recordings, "a01")
    scoped = enforce_tenant_scope(row["sql"])

    assert scoped.predicates_added == 1
    assert scoped.scopes_visited == 2, "the CTE body is a scope and must be visited"
    # The predicate is inside the CTE, where orders actually is.
    cte_body = scoped.sql.split("SELECT * FROM everything")[0]
    assert "tenant_id = %(tenant_id)s" in cte_body


def test_policy_binds_the_tenant_rather_than_interpolating_it(recordings) -> None:
    """The tenant never passes through string formatting.

    A rewriter that builds ``tenant_id = 'acme'`` by formatting is a rewriter with an
    injection vector of its own, and it is why there is no escaping helper anywhere in
    this codebase: there is nothing to escape.
    """
    for row in recordings:
        if row["kind"] != "benign":
            continue
        try:
            scoped = enforce_tenant_scope(row["sql"])
        except PolicyError:
            continue
        assert TENANT_A not in scoped.sql
        assert TENANT_B not in scoped.sql
        if scoped.predicates_added:
            assert "%(tenant_id)s" in scoped.sql


def test_policy_constrains_every_scoped_table_it_reads(recordings) -> None:
    """Across the whole corpus: no statement runs with a scoped table left unconstrained.

    The invariant the rewriter asserts internally, re-asserted here from the outside so
    that removing the internal check does not silently remove the guarantee.
    """
    for row in recordings:
        try:
            scoped = enforce_tenant_scope(row["sql"])
        except PolicyError:
            continue
        scoped_tables = scoped.base_tables & catalog.TENANT_SCOPED
        if scoped_tables:
            assert scoped.predicates_added >= 1, row["id"]
        assert not scoped.unscoped_tables, row["id"]


@pytest.mark.parametrize("case_id", _attack_ids())
def test_policy_handles_every_adversarial_shape(case_id, attack_cases, recordings) -> None:
    """One test per adversarial shape, so a failure names the shape.

    Eighteen cases covering CTEs at one and two levels, ``MATERIALIZED``, set
    operations, correlated and uncorrelated subqueries, ``LATERAL``, set-returning
    functions, comment-terminated predicates, tautologies, catalog probes, statement
    stacking, window partitions, views, ``ORDER BY`` subqueries and quoted identifiers
    -- plus one legitimate cross-tenant question that must be allowed through.
    """
    case = next(c for c in attack_cases if c["id"] == case_id)
    row = recording_by_id(recordings, case_id)

    try:
        scoped = enforce_tenant_scope(row["sql"])
    except PolicyError:
        actual = "refused"
    else:
        actual = "scoped" if scoped.predicates_added else "allowed"

    assert actual == case["expect"], (
        f"{case_id} probes {case['probes']!r}: expected {case['expect']}, got {actual}.\n"
        f"{case['why']}"
    )


def test_a_policy_that_refuses_everything_fails_this_file(attack_cases) -> None:
    """The control, stated as its own test so it cannot be quietly deleted.

    Seventeen of the eighteen cases are satisfied by refusing. If the corpus ever
    contained only those, "refuse every query" would be a passing implementation.
    """
    allowed = [case for case in attack_cases if case["expect"] == "allowed"]
    assert len(allowed) == 1
    assert allowed[0]["id"] == "a18"


# ---------------------------------------------------------------------------
# Layer 2: the database, executing deliberately unscoped SQL
# ---------------------------------------------------------------------------


@pytest.mark.db
def test_rls_blocks_an_unscoped_read(connection) -> None:
    """Row-level security must stop a query the rewriter never touched.

    This runs raw ``SELECT * FROM orders`` -- no predicate, no rewrite -- with
    ``app.tenant_id`` set to ACME. If RLS is working, twenty rows come back. If RLS is
    enabled but inert, forty do, and the service has exactly one layer of defence
    rather than the two it claims.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (TENANT_A,))
        cursor.execute("SELECT tenant_id FROM orders")
        rows = cursor.fetchall()

    assert len(rows) == ORDERS_PER_TENANT, (
        f"expected {ORDERS_PER_TENANT} orders for one tenant, got {len(rows)}. "
        "Row-level security is not constraining this connection."
    )
    assert {row["tenant_id"] for row in rows} == {TENANT_A}


@pytest.mark.db
def test_rls_applies_to_the_connecting_role(connection) -> None:
    """The role the application uses must not be exempt.

    Postgres exempts a table's owner from its policies unless the table is declared
    ``FORCE ROW LEVEL SECURITY``. Both halves are checked: that every fact table forces
    it, and that the role we actually connect as does not own them.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user AS role")
        role = cursor.fetchone()["role"]

        cursor.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   pg_get_userbyid(c.relowner) AS owner
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = ANY(%s)
            """,
            (sorted(catalog.TENANT_SCOPED),),
        )
        tables = cursor.fetchall()

    assert len(tables) == 4
    for table in tables:
        assert table["relrowsecurity"], f"{table['relname']}: RLS is not enabled"
        assert table["relforcerowsecurity"], (
            f"{table['relname']}: RLS is enabled but not FORCEd, so the owner is exempt"
        )
        assert table["owner"] != role, (
            f"{table['relname']}: the application connects as its owner ({role}), "
            "which bypasses row-level security unless FORCE is set"
        )


@pytest.mark.db
def test_rls_fails_closed_when_no_tenant_is_set(connection) -> None:
    """An unset ``app.tenant_id`` must return nothing, not everything."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) AS n FROM orders")
        assert cursor.fetchone()["n"] == 0


@pytest.mark.db
def test_the_application_role_cannot_read_credentials(connection) -> None:
    """``api_keys`` is denied to the role that executes generated SQL."""
    import psycopg

    with connection.cursor() as cursor, pytest.raises(psycopg.errors.InsufficientPrivilege):
        cursor.execute("SELECT * FROM api_keys")


# ---------------------------------------------------------------------------
# Layer 3: the whole pipeline
# ---------------------------------------------------------------------------


@pytest.mark.db
def test_end_to_end_a_cte_question_returns_only_our_rows(ask_as) -> None:
    """The ordinary business question, answered for real.

    'Compare my monthly order totals to last year' is a question Finance asks every
    month. Its generated SQL reads ``orders`` twice, both times inside a CTE. The answer
    must contain this tenant's data and nothing else.
    """
    answer = ask_as(TENANT_A, "Compare my monthly order totals to last year")
    assert answer.scoped.predicates_added == 2
    rendered = json.dumps(answer.as_dict())
    assert TENANT_B not in rendered


@pytest.mark.db
def test_end_to_end_row_counts_do_not_double(ask_as) -> None:
    """The signal a leak actually produces, given identical fixtures.

    Both tenants have twenty orders with the same ids and totals, so a cross-tenant read
    cannot be spotted by looking at the rows. It can only be spotted by counting them.
    """
    answer = ask_as(TENANT_A, "How many orders are in each status?")
    total = sum(int(row["n"]) for row in answer.result.rows)
    assert total == ORDERS_PER_TENANT


@pytest.mark.db
def test_end_to_end_each_tenant_sees_its_own_rows(ask_as) -> None:
    """Asked as either tenant, the answer is that tenant's.

    Equal counts are the expected outcome here -- the fixtures are symmetric. What this
    rules out is a service that returns one tenant's data to both.
    """
    for tenant in (TENANT_A, TENANT_B):
        answer = ask_as(tenant, "How many orders are in each status?")
        rendered = json.dumps(answer.as_dict())
        other = TENANT_B if tenant == TENANT_A else TENANT_A
        assert other not in rendered


@pytest.mark.db
def test_end_to_end_a_refusal_is_audited(ask_as) -> None:
    """The rejection path leaves a record, with the SQL that was refused.

    An audit trail that logs only successes describes a service where nobody has ever
    tried anything, which is the opposite of the truth and useless during an incident.
    """
    from sqlgenie.nl2sql.pipeline import RefusedError

    audit.clear()
    with pytest.raises(RefusedError):
        ask_as(TENANT_A, "What tables exist in this database?")

    entries = audit.records(tenant_id=TENANT_A)
    assert entries, "a refused question left no audit record"
    assert entries[-1].outcome == Outcome.REFUSED
    assert entries[-1].generated_sql, "the refused SQL was not recorded"


@pytest.mark.db
def test_end_to_end_the_audit_holds_the_sql_that_ran(ask_as) -> None:
    """Not the SQL that was generated. They differ by the predicate, which is the
    entire thing an investigator needs to see."""
    audit.clear()
    answer = ask_as(TENANT_A, "What is the average order value?")

    entry = audit.records(tenant_id=TENANT_A)[-1]
    assert entry.outcome == Outcome.EXECUTED
    assert entry.executed_sql == answer.executed_sql
    assert "%(tenant_id)s" in entry.executed_sql
    assert "%(tenant_id)s" not in entry.generated_sql
