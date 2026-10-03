"""The HTTP surface.

Driven against the real application and a real database. The endpoints are thin enough
that mocking what sits under them would leave nothing under test, and the things worth
getting wrong here are exactly what a mock would hide: that the tenant comes from the
key, that the schema endpoint exposes no data, and that the audit trail is itself
treated as tenant data.

These tests open their own connections through ``pool.app_connection`` rather than using
the rolled-back ``connection`` fixture, because that is what the application does. They
are read-only, so the seeded database is unchanged by running them.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from sqlgenie.api import create_app
from sqlgenie.config import Settings
from sqlgenie.nl2sql import audit
from tests.conftest import REPO_ROOT, TENANT_A, TENANT_B

pytestmark = pytest.mark.db

#: Seeded keys. The third one is deliberately revoked.
KEY_A = "acme-dev-key"
KEY_B = "borg-dev-key"
REVOKED_KEY = "acme-retired-key"


@pytest.fixture
def client() -> Iterator[TestClient]:
    """The real app, pointed at the repository's fixtures."""
    with TestClient(create_app(Settings(root=REPO_ROOT))) as test_client:
        yield test_client


def ask(client: TestClient, key: str, question: str):
    """POST a question with an API key."""
    return client.post("/v1/ask", json={"question": question}, headers={"X-Api-Key": key})


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_a_question_needs_a_key(client: TestClient) -> None:
    assert client.post("/v1/ask", json={"question": "What is the average order value?"}).status_code == 401


def test_an_unknown_key_is_rejected(client: TestClient) -> None:
    assert ask(client, "not-a-real-key", "What is the average order value?").status_code == 401


def test_a_revoked_key_is_rejected(client: TestClient) -> None:
    """**A key that was rotated out must stop working.**

    ``api_keys`` carries ``revoked_at`` and the row stays in the table after rotation --
    deleting it would destroy the audit trail of which key did what. So revocation is a
    column that has to be *checked*, and a lookup that finds the row and stops there
    authenticates every key the service has ever issued.

    The seeded fixture includes exactly one revoked key so this is testable at all.
    """
    response = ask(client, REVOKED_KEY, "What is the average order value?")
    assert response.status_code == 401


def test_rejection_does_not_say_why(client: TestClient) -> None:
    """Unknown and revoked produce the same message.

    Distinguishing them confirms which keys once existed, which is a slow enumeration
    oracle and buys a legitimate caller nothing.
    """
    unknown = ask(client, "not-a-real-key", "What is the average order value?").json()
    revoked = ask(client, REVOKED_KEY, "What is the average order value?").json()
    assert unknown["detail"] == revoked["detail"]


# ---------------------------------------------------------------------------
# The schema endpoint
# ---------------------------------------------------------------------------


def test_schema_lists_tables_and_columns(client: TestClient) -> None:
    body = client.get("/v1/schema", headers={"X-Api-Key": KEY_A}).json()
    names = {table["name"] for table in body["tables"]}
    assert names == {"customers", "orders", "order_items", "products", "plans"}


def test_schema_exposes_no_data(client: TestClient) -> None:
    """**Names only. No values, no counts, no ranges.**

    Sample values are the thing somebody asks for to help the model pick the right
    column, and they turn this endpoint into a way to read another tenant's data one
    statistic at a time -- no query, no audit record, no tenant predicate anywhere near
    it, because nobody thinks of a schema endpoint as a data path.

    Asserted against the seeded values directly: if any customer name, email or SKU
    appears in the schema response, the endpoint has started returning rows.
    """
    body = client.get("/v1/schema", headers={"X-Api-Key": KEY_A}).text
    for leaked in ("Dana Whitfield", "dana@acme.example", "SKU-100", "Borg Industries"):
        assert leaked not in body, f"the schema endpoint returned data: {leaked!r}"

    for table in client.get("/v1/schema", headers={"X-Api-Key": KEY_A}).json()["tables"]:
        assert set(table) <= {"name", "columns", "tenant_scoped", "description"}


def test_schema_needs_a_key(client: TestClient) -> None:
    assert client.get("/v1/schema").status_code == 401


# ---------------------------------------------------------------------------
# Asking
# ---------------------------------------------------------------------------


def test_each_tenant_gets_its_own_rows(client: TestClient) -> None:
    """**The test that catches a cache keyed without a tenant.**

    Both tenants hold identical data, so comparing the *values* in two answers proves
    nothing -- they are supposed to match. What distinguishes them is the ``tenant_id``
    column, which is why one benign recording selects it.

    Ask as ACME, then as BORG, and each must see its own tenant id. A response cache, a
    memoised lookup or a process-wide "current tenant" that drops the tenant from its
    key passes every other test in this file and fails this one.
    """
    first = ask(client, KEY_A, "Show me my ten most recent orders")
    second = ask(client, KEY_B, "Show me my ten most recent orders")
    assert first.status_code == second.status_code == 200

    acme_rows = first.json()["rows"]
    borg_rows = second.json()["rows"]
    assert acme_rows and borg_rows
    assert {row["tenant_id"] for row in acme_rows} == {TENANT_A}
    assert {row["tenant_id"] for row in borg_rows} == {TENANT_B}


def test_asking_twice_in_the_other_order_still_scopes(client: TestClient) -> None:
    """The same property with the tenants reversed.

    A cache populated by the first caller returns that caller's rows to the second, so
    whichever tenant asks first would pass on its own. Running both orders means neither
    position is the lucky one.
    """
    borg_first = ask(client, KEY_B, "Show me my ten most recent orders").json()["rows"]
    acme_second = ask(client, KEY_A, "Show me my ten most recent orders").json()["rows"]
    assert {row["tenant_id"] for row in borg_first} == {TENANT_B}
    assert {row["tenant_id"] for row in acme_second} == {TENANT_A}


def test_a_refused_question_is_a_400(client: TestClient) -> None:
    """Not a 500. A refusal is understood and will never work; an error might.

    Collapsing the two puts a probing attacker in the same bucket as a database outage
    and pages somebody for the wrong reason.
    """
    assert ask(client, KEY_A, "What tables exist in this database?").status_code == 400


def test_an_unrecorded_question_is_refused(client: TestClient) -> None:
    assert ask(client, KEY_A, "something nobody ever recorded an answer for").status_code == 400


# ---------------------------------------------------------------------------
# The audit endpoint
# ---------------------------------------------------------------------------


def test_the_audit_trail_is_scoped_to_its_tenant(client: TestClient) -> None:
    """**The audit trail of a multi-tenant service is itself tenant data.**

    It holds the questions people asked and the SQL that ran, which is a more concise
    description of a competitor's business than most of the tables it queries. An audit
    endpoint returning every record would be the most efficient cross-tenant read in the
    product, and it would be reached by a caller who never ran a single query.
    """
    # Two questions used by no other test in the suite. Deliberate: a question another
    # test has already asked may have been answered from somewhere else by the time this
    # runs, and then this test is asserting on an empty trail rather than on scoping.
    audit.clear()
    ask(client, KEY_A, "How many orders did we take last month?")
    ask(client, KEY_B, "What is the average number of items per order?")

    acme = client.get("/v1/audit", headers={"X-Api-Key": KEY_A}).json()["records"]
    borg = client.get("/v1/audit", headers={"X-Api-Key": KEY_B}).json()["records"]

    assert acme and borg
    assert {record["tenant_id"] for record in acme} == {TENANT_A}
    assert {record["tenant_id"] for record in borg} == {TENANT_B}

    acme_questions = {record["question"] for record in acme}
    assert "What is the average number of items per order?" not in acme_questions


def test_the_audit_endpoint_needs_a_key(client: TestClient) -> None:
    assert client.get("/v1/audit").status_code == 401


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_healthz_is_open(client: TestClient) -> None:
    """Liveness takes no key: a probe that needs a credential is a probe that fails
    for the wrong reason the day the credential is rotated."""
    assert client.get("/healthz").json() == {"status": "ok"}


def test_readyz_reports_both_dependencies(client: TestClient) -> None:
    body = client.get("/readyz").json()
    assert body["database"] is True
    assert body["cassettes"] == 31
