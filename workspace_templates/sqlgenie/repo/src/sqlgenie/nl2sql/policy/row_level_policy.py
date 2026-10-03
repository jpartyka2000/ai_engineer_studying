"""Row-level tenant scoping, applied to generated SQL before it is executed.

**This module is the security boundary.** The model is not: a prompt that asks for
tenant-scoped SQL is a request, not a constraint, and anything that treats the
generator's cooperation as a defence has no defence. Postgres row-level security sits
underneath as a second layer, but RLS is a backstop for mistakes here rather than a
replacement for this.

The rewrite walks **scopes, not tables.** A SQL statement is a tree of query scopes --
the outer select, each CTE body, each derived table, each branch of a set operation,
each lateral -- and every one of them can reference a base table independently. Scoping
only the statement's outermost scope leaves every other one unconstrained, and the
resulting query is syntactically fine, returns plausible rows, and reads the whole
table. :func:`sqlglot.optimizer.scope.traverse_scope` enumerates them all and resolves
derived sources away, so a CTE name is never mistaken for a table.

**The policy fails closed.** A reference it cannot resolve to a known table raises
rather than being skipped. That is the difference between a rewriter that enforces
something and one that appears to: the silent-skip version is indistinguishable from
correct right up until somebody writes a query shape nobody anticipated.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

from sqlgenie.nl2sql import catalog

logger = logging.getLogger(__name__)

#: Dialect used for both parsing and rendering. One dialect throughout, because a
#: statement parsed as one and rendered as another is a statement nobody reviewed.
DIALECT = "postgres"

#: Name of the bound parameter the predicate references. Rendered by sqlglot as
#: ``%(tenant_id)s`` for psycopg, so the value is **bound, never interpolated** -- the
#: tenant id does not pass through string formatting at any point.
TENANT_PARAM = "tenant_id"


class PolicyError(Exception):
    """Raised when a statement cannot be safely scoped.

    Always fatal to the request. There is no "scope it partially and run it anyway"
    outcome, because a partially scoped query is an unscoped query with extra steps.
    """


@dataclass(frozen=True)
class ScopedQuery:
    """The result of rewriting one statement.

    Attributes:
        sql: The rewritten SQL, with a bound tenant predicate on every scoped
            reference.
        base_tables: Every base table the statement reads, CTE names resolved away.
        predicates_added: How many tenant predicates were inserted. Zero is a
            legitimate answer only when the statement touches no scoped table at all,
            and the executor checks that rather than assuming it.
        scopes_visited: How many query scopes the rewrite walked. Carried because "one"
            on a statement with a CTE is the signature of a traversal that stopped at
            the top.
    """

    sql: str
    base_tables: frozenset[str] = frozenset()
    predicates_added: int = 0
    scopes_visited: int = 0
    unscoped_tables: frozenset[str] = field(default_factory=frozenset)

    @property
    def touches_tenant_data(self) -> bool:
        """Whether any tenant-scoped table is referenced."""
        return bool(self.base_tables & catalog.TENANT_SCOPED)


def parse(sql: str) -> exp.Expression:
    """Parse one statement, rejecting anything that is not a single statement.

    Args:
        sql: Generated SQL.

    Returns:
        The parsed expression.

    Raises:
        PolicyError: If the text is empty, unparseable, or contains more than one
            statement. Statement stacking is how ``SELECT 1; DROP TABLE orders`` gets
            past a check that only ever looked at the first one.
    """
    try:
        statements = [s for s in sqlglot.parse(sql, read=DIALECT) if s is not None]
    except sqlglot.ParseError as exc:
        raise PolicyError(f"could not parse generated SQL: {exc}") from exc

    if not statements:
        raise PolicyError("generated SQL was empty")
    if len(statements) > 1:
        raise PolicyError(
            f"expected a single statement, got {len(statements)}; statement stacking is refused"
        )
    return statements[0]


def collect_base_tables(expression: exp.Expression) -> frozenset[str]:
    """Return every base table a statement reads, with derived names resolved away.

    A CTE name and a derived-table alias are *not* base tables -- they are names for
    other scopes, and those scopes are walked in their own right. Treating them as
    tables is how ``WITH t AS (SELECT * FROM orders) SELECT * FROM t`` ends up reporting
    its only table as ``t``, which is in no catalog and therefore gets no predicate.

    Args:
        expression: A parsed statement.

    Returns:
        Lower-cased base table names.
    """
    tables: set[str] = set()
    for scope in traverse_scope(expression):
        for source in scope.sources.values():
            if isinstance(source, exp.Table):
                tables.add(source.name.lower())
    return frozenset(tables)


def enforce_tenant_scope(sql: str, *, strict: bool = True) -> ScopedQuery:
    """Add a bound tenant predicate to every scoped base-table reference.

    Args:
        sql: Generated SQL, a single SELECT statement.
        strict: Whether an unknown table is fatal. Always ``True`` in the request path;
            the parameter exists so the catalog-coverage test can enumerate what a
            non-strict pass would have skipped, and **not** so a caller can turn the
            check off.

    Returns:
        A :class:`ScopedQuery`.

    Raises:
        PolicyError: If the statement cannot be parsed, is not a single statement, or
            references a table the catalog does not know while ``strict``.

    Example:
        ``WITH t AS (SELECT * FROM orders) SELECT * FROM t`` becomes
        ``WITH t AS (SELECT * FROM orders WHERE orders.tenant_id = %(tenant_id)s)
        SELECT * FROM t`` -- the predicate lands inside the CTE, where the base table
        actually is.
    """
    tree = parse(sql)

    added = 0
    visited = 0
    tables: set[str] = set()
    unscoped: set[str] = set()
    scoped: set[str] = set()

    for scope in traverse_scope(tree):
        visited += 1
        # Not every scope is a SELECT. A LATERAL, for instance, is its own scope whose
        # sources are visible to the select that encloses it, and that enclosing select
        # is where the predicate belongs. Skipping it here is only safe because of the
        # coverage assertion below -- without that, this `continue` would be exactly the
        # silent skip this module exists to avoid.
        if not isinstance(scope.expression, exp.Select):
            continue

        for alias, source in scope.sources.items():
            # A derived source -- a CTE body, a subquery, a lateral -- is a scope of its
            # own and is visited by this same loop. Scoping it here as though it were a
            # table would constrain the wrong level and miss the real one.
            if not isinstance(source, exp.Table):
                continue

            # A table-valued function -- generate_series(), unnest(), a set-returning
            # function -- parses as a Table whose `this` is the call rather than an
            # identifier, so it has no name to look up. Named explicitly because
            # otherwise it falls through to the unknown-table branch and refuses with
            # "'' is not a table", which tells whoever is reading the log nothing.
            if not isinstance(source.this, exp.Identifier):
                if strict:
                    raise PolicyError(
                        "refusing to execute: a table-valued function is used as a "
                        "query source. The policy cannot determine which rows such a "
                        "source returns, so it cannot constrain them."
                    )
                unscoped.add(source.sql(dialect=DIALECT))
                continue

            name = source.name.lower()
            tables.add(name)

            if not catalog.is_known(name):
                if strict:
                    raise PolicyError(
                        f"refusing to execute: {name!r} is not a table this service knows. "
                        "An unresolvable reference is not scoped, and an unscoped "
                        "reference is a cross-tenant read."
                    )
                unscoped.add(name)
                continue

            if not catalog.is_tenant_scoped(name):
                continue

            qualifier = alias or name
            scope.expression.where(
                f"{qualifier}.{catalog.TENANT_COLUMN} = :{TENANT_PARAM}",
                append=True,
                copy=False,
            )
            added += 1
            scoped.add(name)

    # The closing invariant, and the reason any of the `continue`s above are safe: every
    # tenant-scoped table this statement reads must have received a predicate somewhere.
    # Checked rather than assumed, because the failure it catches -- a reference in a
    # scope shape the walk did not place a predicate into -- produces a query that runs
    # fine and returns other tenants' rows.
    missed = {name for name in tables if name in catalog.TENANT_SCOPED} - scoped
    if missed and strict:
        raise PolicyError(
            f"refusing to execute: no tenant predicate was placed for {sorted(missed)}. "
            "The statement reads tenant data through a construct this policy could not "
            "constrain."
        )
    unscoped |= missed

    rewritten = tree.sql(dialect=DIALECT)
    logger.debug("scoped %d reference(s) across %d scope(s)", added, visited)
    return ScopedQuery(
        sql=rewritten,
        base_tables=frozenset(tables),
        predicates_added=added,
        scopes_visited=visited,
        unscoped_tables=frozenset(unscoped),
    )
