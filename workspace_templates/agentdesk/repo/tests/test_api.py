"""The HTTP surface, against the seeded database.

Marked ``db`` throughout. These are the tests that would catch the FastAPI annotation
trap described at the top of :mod:`agentdesk.api`: a body model that FastAPI cannot
resolve becomes a query parameter, and every POST starts answering 422 while every unit
test stays green.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentdesk.api import app

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True, scope="module")
def restore_seeded_tickets():
    """Delete anything this module created, however it ended.

    **Not tidiness -- correctness, twice over.**

    Tool output is part of the cassette key, and ``search_tickets`` reads the ticket
    table. A ticket left behind by this module changes what a later test's search
    returns, which changes the key, which surfaces as a cassette miss in
    ``test_cassette_consistency.py`` -- a file that did nothing wrong and names nothing
    useful in its failure.

    It is also what makes ``make test`` repeatable. Without this, the suite passes once
    on a fresh database and fails on the second run, which is the worst possible
    behaviour for a repository somebody is working in.
    """
    from agentdesk import db

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT coalesce(max(id), 0) FROM tickets")
        high_water = cur.fetchone()[0]
        conn.commit()

    yield

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM tickets WHERE id > %s", (high_water,))
        conn.commit()


def test_health_reports_the_database_and_the_clock(client: TestClient) -> None:
    payload = client.get("/health").json()
    assert payload["status"] == "ok"
    assert payload["database"] is True
    assert payload["clock_pinned"] is True, (
        "the clock must be pinned, or every cassette key drifts with the wall clock"
    )


def test_the_queue_lists_tickets_worst_first(client: TestClient) -> None:
    payload = client.get("/tickets").json()
    assert payload["banner"]["total"] > 0
    first = payload["tickets"][0]
    assert first["summary"]


def test_a_missing_ticket_is_a_404(client: TestClient) -> None:
    assert client.get("/tickets/99999").status_code == 404


def test_one_ticket_carries_its_sla_state(client: TestClient) -> None:
    payload = client.get("/tickets/1").json()
    assert payload["id"] == 1
    assert set(payload["sla"]) == {"due_at", "remaining_seconds", "breached", "at_risk"}


def test_search_finds_the_printer_ticket(client: TestClient) -> None:
    hits = client.get("/search", params={"q": "printer jams"}).json()["hits"]
    assert hits
    assert any("printer" in hit["ticket"]["subject"].lower() for hit in hits)


def test_the_dashboard_renders(client: TestClient) -> None:
    payload = client.get("/dashboard").json()
    assert payload["rows"]
    assert all(row["summary"] for row in payload["rows"])


def test_drafting_a_reply_returns_its_working(client: TestClient) -> None:
    """**A POST with a body.** If the request model stopped resolving, this is a 422."""
    response = client.post(
        "/assistant/draft",
        json={"ticket_id": 2, "question": "What should I tell them about the VPN?"},
    )
    assert response.status_code == 200, response.text

    payload = response.json()
    assert payload["gave_up"] is False
    assert [step["tool"] for step in payload["steps"]] == ["lookup_ticket", "kb_article"]
    assert "#2" in payload["citations"]
    assert payload["draft_id"]


def test_drafting_against_a_missing_ticket_is_a_404(client: TestClient) -> None:
    response = client.post(
        "/assistant/draft", json={"ticket_id": 99999, "question": "anything"}
    )
    assert response.status_code == 404


def test_the_fence_preview_shows_a_neutralized_marker(client: TestClient) -> None:
    """Ticket 5 carries a forged closing marker. An operator must be able to confirm,
    rather than assume, that it was defused."""
    payload = client.get("/assistant/fence-preview/5").json()
    rendered = payload["as_the_model_sees_it"]
    assert rendered.count("<<<END:ticket>>>") == 1
    assert "[marker removed]" in rendered


def test_creating_a_ticket_summarizes_it_once(client: TestClient) -> None:
    response = client.post(
        "/tickets",
        json={
            "subject": "Printer offline",
            "body": "The printer by the kitchen has been offline since Monday.",
            "requester": "new.person@northgate.example",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["summary"] == "Kitchen printer offline since Monday."
    assert payload["status"] == "open"


def test_creating_a_ticket_without_a_subject_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/tickets", json={"subject": "", "body": "x", "requester": "a@b.example"}
    )
    assert response.status_code == 422


def test_the_serving_plan_adds_up(client: TestClient) -> None:
    payload = client.get("/serving/plan").json()
    assert (
        payload["weight_bytes"] + payload["reserved_bytes"] + payload["kv_available_bytes"]
        == payload["vram_bytes"]
    )
    assert payload["total_blocks"] > 0
    assert payload["free_blocks"] == payload["total_blocks"]


def test_admission_refuses_more_than_the_card_holds(client: TestClient) -> None:
    payload = client.post(
        "/serving/admit",
        json={"prompt_tokens": 900, "max_new_tokens": 200, "concurrent": 500},
    ).json()
    assert payload["admitted"] < payload["requested"]
    assert payload["verdicts"][-1]["verdict"] == "no_capacity"


def test_a_request_too_large_for_the_card_says_so(client: TestClient) -> None:
    """``too_large`` and ``no_capacity`` are different answers: one means stop retrying."""
    payload = client.post(
        "/serving/admit",
        json={"prompt_tokens": 8000, "max_new_tokens": 100, "concurrent": 1},
    ).json()
    assert payload["verdicts"][0]["verdict"] in {"too_large", "admitted"}
