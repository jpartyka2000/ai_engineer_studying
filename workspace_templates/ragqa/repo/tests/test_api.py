"""The HTTP surface, driven against the real application and a real database.

The handlers are thin enough that mocking what sits under them would leave nothing under
test. What is worth getting wrong here is the error mapping and the history scoping, and
a mock would hide both.
"""

from __future__ import annotations

import uuid
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from ragqa.api import create_app
from ragqa.config import Settings
from tests.conftest import REPO_ROOT

pytestmark = pytest.mark.db


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """The real app, pointed at the repository's corpus and fixtures."""
    with TestClient(create_app(Settings(root=REPO_ROOT, database_url=settings.database_url))) as c:
        yield c


def ask(client: TestClient, question: str, session_id: str | None = None):
    """POST a question."""
    payload = {"question": question}
    if session_id:
        payload["session_id"] = session_id
    return client.post("/v1/ask", json=payload)


def test_healthz_touches_nothing(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_readyz_reports_the_index_and_the_fixtures(client: TestClient) -> None:
    body = client.get("/readyz").json()
    assert body["status"] == "ready"
    assert body["chunks"] > 0
    assert body["cassettes"] == 27


def test_the_corpus_endpoint_lists_titles_not_text(client: TestClient) -> None:
    """Returning passage text would make this a way to read the whole knowledge base
    without asking a question, which is not what it is for."""
    body = client.get("/v1/corpus").json()
    assert len(body["documents"]) == 27
    rendered = str(body)
    assert "Employees accrue 25 days" not in rendered


def test_an_answerable_question_is_answered(client: TestClient) -> None:
    body = ask(client, "How long is probation?").json()
    assert body["refused"] is False
    assert "three months" in body["answer"]
    assert body["citations"]


def test_a_refusal_is_a_200(client: TestClient) -> None:
    """**Not a 4xx.**

    The system was asked a question and gave its honest answer, which happens to be that
    it does not know. A 4xx would make "we have no documentation on this" look like a
    malformed request and would put every gap in the corpus into the error rate.
    """
    response = ask(client, "How do I cook a risotto?")
    assert response.status_code == 200
    assert response.json()["refused"] is True


def test_a_question_is_required(client: TestClient) -> None:
    assert client.post("/v1/ask", json={}).status_code == 422
    assert client.post("/v1/ask", json={"question": ""}).status_code == 422


def test_unknown_fields_are_rejected(client: TestClient) -> None:
    """A typo in a caller's payload should fail loudly rather than be ignored."""
    assert client.post("/v1/ask", json={"question": "hi", "top_k": 9}).status_code == 422


def test_a_session_id_is_issued_when_none_is_given(client: TestClient) -> None:
    body = ask(client, "When are salaries paid?").json()
    assert body["session_id"]
    uuid.UUID(body["session_id"])


def test_history_is_scoped_to_its_session(client: TestClient) -> None:
    """**A conversation is a list of the things somebody did not know.**

    That is not a list they would choose to share with colleagues, so history is scoped
    to the session that produced it.
    """
    first = str(uuid.uuid4())
    second = str(uuid.uuid4())
    ask(client, "How long is probation?", first)
    ask(client, "When are salaries paid?", second)

    first_turns = client.get(f"/v1/sessions/{first}/history").json()["turns"]
    second_turns = client.get(f"/v1/sessions/{second}/history").json()["turns"]

    assert [t["question"] for t in first_turns] == ["How long is probation?"]
    assert [t["question"] for t in second_turns] == ["When are salaries paid?"]


def test_history_records_refusals_too(client: TestClient) -> None:
    """A refusal is the most interesting thing in a conversation log: it is a question
    the knowledge base could not answer, which is how corpus gaps get found."""
    session = str(uuid.uuid4())
    ask(client, "What is the capital of Peru?", session)
    turns = client.get(f"/v1/sessions/{session}/history").json()["turns"]
    assert len(turns) == 1
    assert turns[0]["refused"] is True


def test_an_unknown_session_has_an_empty_history(client: TestClient) -> None:
    body = client.get(f"/v1/sessions/{uuid.uuid4()}/history").json()
    assert body["turns"] == []


def test_history_is_newest_first(client: TestClient) -> None:
    session = str(uuid.uuid4())
    ask(client, "How long is probation?", session)
    ask(client, "When are salaries paid?", session)
    turns = client.get(f"/v1/sessions/{session}/history").json()["turns"]
    assert turns[0]["question"] == "When are salaries paid?"
