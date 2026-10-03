"""The catalog is data, not a query.

``TABLES`` is a Python dict. Rendering it into the prompt's schema section must not
touch the database, and that is a performance property *and* a correctness one:

**Performance.** ``schema_prompt_section`` is called once per question, on the request
path. A version that asks the database what columns exist turns every question into a
round trip per table before any work starts, and the cost grows with the number of
tables rather than with traffic.

**Correctness.** The rendered section is part of the cassette key. If it were derived
from the live database, the key would depend on the state of a schema that migrations
change -- so a deploy would silently invalidate every recorded response, and the service
would start refusing questions it answered yesterday for no reason anybody could see.

These tests count calls rather than forbidding them with an exception, deliberately. Code
that reaches for a connection inside a ``try/except Exception: pass`` -- which is exactly
how a well-meant advisory check gets written -- would sail past an assertion that merely
expects a raise.
"""

from __future__ import annotations

import pytest

from sqlgenie.nl2sql import catalog, prompt


@pytest.fixture
def connection_counter(monkeypatch) -> dict[str, int]:
    """Count every attempt to open a database connection."""
    counts = {"owner": 0, "app": 0}

    from sqlgenie.db import pool

    def fake_owner(*args, **kwargs):
        counts["owner"] += 1
        raise AssertionError("the catalog must not open a database connection")

    def fake_app(*args, **kwargs):
        counts["app"] += 1
        raise AssertionError("the catalog must not open a database connection")

    monkeypatch.setattr(pool, "owner_connection", fake_owner)
    monkeypatch.setattr(pool, "app_connection", fake_app)
    return counts


def test_rendering_the_schema_section_opens_no_connection(connection_counter) -> None:
    """The render is pure. Counted, not merely unraised."""
    rendered = catalog.schema_prompt_section()
    assert "orders(" in rendered
    assert connection_counter == {"owner": 0, "app": 0}


def test_building_a_prompt_opens_no_connection(connection_counter) -> None:
    """The whole prompt path, which is what the request actually calls."""
    built = prompt.build_prompt("How many orders are in each status?")
    assert "Schema:" in built
    assert connection_counter == {"owner": 0, "app": 0}


def test_the_schema_section_is_stable_across_calls() -> None:
    """Byte-identical every time, or the cassette keys move between requests."""
    assert catalog.schema_prompt_section() == catalog.schema_prompt_section()


def test_the_schema_section_is_deterministically_ordered() -> None:
    """Sorted by table name. Dict iteration order is stable in CPython but is not a
    contract anybody should be staking a cache key on."""
    rendered = catalog.schema_prompt_section().splitlines()
    names = [line.split("(", 1)[0] for line in rendered]
    assert names == sorted(names)


def test_shared_reference_data_is_not_tenant_scoped() -> None:
    """``plans`` is the control for the whole policy.

    A rewriter that adds a tenant predicate to every table it sees is not enforcing a
    rule, it is applying a reflex, and this is the only table where the difference shows.
    """
    assert catalog.TENANT_SCOPED == {"customers", "orders", "order_items", "products"}
    assert not catalog.is_tenant_scoped("plans")


def test_an_unknown_table_raises_rather_than_returning_false() -> None:
    """The caller is a security policy deciding whether to constrain a reference.

    ``False`` would mean "no predicate needed", which for something unidentifiable is
    the one answer that is never safe.
    """
    with pytest.raises(catalog.UnknownTableError):
        catalog.is_tenant_scoped("pg_tables")


# ---------------------------------------------------------------------------
# The request path's cost
# ---------------------------------------------------------------------------


@pytest.mark.db
def test_answering_a_question_makes_a_fixed_number_of_round_trips(client, settings) -> None:
    """Answering one question costs a fixed number of statements, whatever the schema.

    The floor is three on the request connection: the statement timeout, the tenant
    setting, and the query itself. Nothing in the request path may ask the database
    about its own schema -- that cost grows with the number of tables rather than with
    traffic, and it is paid before any useful work begins.

    Counted on the connection the pipeline is handed, which is the same thing
    bench/bench_ask.py measures.
    """
    from sqlgenie.db import pool
    from sqlgenie.nl2sql import pipeline
    from sqlgenie.tenancy import context

    statements: list[str] = []

    class CountingCursor:
        def __init__(self, inner):
            self._inner = inner

        def execute(self, query, params=None, **kwargs):
            statements.append(str(query))
            return self._inner.execute(query, params, **kwargs)

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def __enter__(self):
            self._inner.__enter__()
            return self

        def __exit__(self, *args):
            return self._inner.__exit__(*args)

    class CountingConnection:
        def __init__(self, inner):
            self._inner = inner

        def cursor(self, *args, **kwargs):
            return CountingCursor(self._inner.cursor(*args, **kwargs))

        def __getattr__(self, name):
            return getattr(self._inner, name)

    # A question no other test asks. Deliberate: if another test has already asked it,
    # anything memoising answers would let this one through on zero statements, and the
    # count being asserted would be the count of a cache hit.
    with context.bind_tenant("acme"), pool.app_connection(settings) as raw:
        pipeline.ask(
            "List the products in the Outdoor category",
            connection=CountingConnection(raw),
            client=client,
            tenant_id="acme",
            max_rows=settings.max_rows,
            statement_timeout_ms=settings.statement_timeout_ms,
        )

    assert len(statements) == 3, f"expected 3 statements, got {len(statements)}: {statements}"
    catalog_probes = [s for s in statements if "information_schema" in s or "pg_catalog" in s]
    assert not catalog_probes, f"the request path queried the schema: {catalog_probes}"
