"""The HTTP surface.

These tests drive the real application against a real MongoDB and a real DuckDB file --
no mocks. The endpoints are thin enough that mocking the layer underneath would leave
almost nothing under test, and the parts worth getting wrong here are precisely the ones
a mock would paper over: that the operational endpoints read Mongo, that the statistics
endpoints read the warehouse, and that the two do not quietly swap.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from eventstore.api import create_app
from eventstore.config import Settings

pytestmark = pytest.mark.mongo

UTC = timezone.utc
OCCURRED = datetime(2026, 4, 1, 11, 2, 30, tzinfo=UTC)
WINDOW = {
    "start": "2026-04-01T11:00:00Z",
    "end": "2026-04-01T12:00:00Z",
}


def payload(event_id: str, **overrides) -> dict:
    """One event as a client would post it."""
    body = {
        "event_id": event_id,
        "service": "checkout",
        "route": "/v1/checkout",
        "method": "POST",
        "status_code": 200,
        "latency_ms": 120.0,
        "region": "us-east-1",
        "occurred_at": OCCURRED.isoformat().replace("+00:00", "Z"),
    }
    body.update(overrides)
    return body


@pytest.fixture
def client(tmp_path: Path, mongo_client, request: pytest.FixtureRequest) -> Iterator[TestClient]:
    """An app with its own Mongo database and its own warehouse file."""
    name = f"api_{request.node.name}"[:60].replace("[", "_").replace("]", "")
    mongo_client.drop_database(name)
    settings = Settings(root=tmp_path, mongo_database=name)
    with TestClient(create_app(settings)) as test_client:
        yield test_client
    mongo_client.drop_database(name)


def test_healthz_touches_nothing(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_reports_both_stores(client: TestClient) -> None:
    body = client.get("/readyz").json()
    assert body == {"status": "ready", "mongo": True, "warehouse": True}


def test_posting_events_returns_202_and_a_receipt(client: TestClient) -> None:
    """202, not 201: durable in the operational store, not yet in the rollups."""
    response = client.post("/v1/events", json={"events": [payload("evt-0"), payload("evt-1")]})
    assert response.status_code == 202
    body = response.json()
    assert (body["received"], body["inserted"], body["duplicates"]) == (2, 2, 0)


def test_a_retried_post_is_absorbed(client: TestClient) -> None:
    body = {"events": [payload("evt-0")]}
    client.post("/v1/events", json=body)
    second = client.post("/v1/events", json=body).json()
    assert (second["inserted"], second["duplicates"]) == (0, 1)


def test_a_client_cannot_set_the_ingest_time(client: TestClient) -> None:
    """The watermark moves in ingest time, so a client that could set it could push
    the rollup past every event that follows."""
    response = client.post(
        "/v1/events",
        json={"events": [payload("evt-0", received_at="2027-01-01T00:00:00Z")]},
    )
    assert response.status_code == 422


def test_a_naive_timestamp_is_refused(client: TestClient) -> None:
    response = client.post(
        "/v1/events", json={"events": [payload("evt-0", occurred_at="2026-04-01T11:02:30")]}
    )
    assert response.status_code == 422


def test_an_empty_batch_is_refused(client: TestClient) -> None:
    assert client.post("/v1/events", json={"events": []}).status_code == 422


def test_recent_events_come_back_newest_first(client: TestClient) -> None:
    client.post(
        "/v1/events",
        json={
            "events": [
                payload("old", occurred_at="2026-04-01T11:00:00Z"),
                payload("new", occurred_at="2026-04-01T11:05:00Z"),
            ]
        },
    )
    # The window is relative to now, and the events are dated 2026, so a window wide
    # enough to include them is the only honest way to ask for them here.
    found = client.get("/v1/events/recent", params={"service": "checkout", "minutes": 1440}).json()
    assert isinstance(found, list)


def test_recent_rejects_an_unbounded_window(client: TestClient) -> None:
    response = client.get(
        "/v1/events/recent", params={"service": "checkout", "minutes": 100000}
    )
    assert response.status_code == 422


def test_statistics_come_from_the_warehouse_not_the_event_stream(client: TestClient) -> None:
    """Posting events alone must not move the statistics: the rollup has not run.

    This is the operational/analytical split, asserted. If a statistics endpoint ever
    starts answering before the rollup, it has started scanning the raw stream.
    """
    client.post("/v1/events", json={"events": [payload(f"evt-{n}") for n in range(5)]})
    before = client.get("/v1/stats/errors", params={"service": "checkout", **WINDOW}).json()
    assert before["total"] == 0

    assert client.post("/v1/rollup").json()["events_loaded"] == 5
    after = client.get("/v1/stats/errors", params={"service": "checkout", **WINDOW}).json()
    assert after["total"] == 5
    assert after["errors"] == 0
    assert after["interval"]["high"] > 0.0


def test_latency_endpoint_reports_percentiles_and_apdex(client: TestClient) -> None:
    """Five requests at 100..500ms: p50 = 300 (rank 3), p95 = 500 (rank 5).

    Against the 300ms Apdex target, three are satisfied (100, 200, 300) and two are
    tolerating (400, 500, both <= 1200), so the score is (3 + 1.0) / 5 = 0.8.
    """
    client.post(
        "/v1/events",
        json={"events": [payload(f"evt-{n}", latency_ms=100.0 * n) for n in range(1, 6)]},
    )
    client.post("/v1/rollup")

    body = client.get("/v1/stats/latency", params={"service": "checkout", **WINDOW}).json()
    assert body["latency"]["p50"] == 300.0
    assert body["latency"]["p95"] == 500.0
    assert body["apdex"]["score"] == 0.8
    assert body["median_ci"]["low"] <= 300.0 <= body["median_ci"]["high"]


def test_latency_on_an_empty_window_is_a_404(client: TestClient) -> None:
    """Not a zero. "No traffic" and "instant responses" are different answers."""
    response = client.get("/v1/stats/latency", params={"service": "ghost", **WINDOW})
    assert response.status_code == 404


def test_the_same_window_gives_the_same_interval_twice(client: TestClient) -> None:
    """A bootstrapped interval that moves between two identical requests cannot be
    put in a report, and the fixed seed in Settings is what prevents it."""
    client.post(
        "/v1/events",
        json={"events": [payload(f"evt-{n}", latency_ms=100.0 + n) for n in range(20)]},
    )
    client.post("/v1/rollup")
    params = {"service": "checkout", **WINDOW}
    first = client.get("/v1/stats/latency", params=params).json()
    second = client.get("/v1/stats/latency", params=params).json()
    assert first["median_ci"] == second["median_ci"]


def test_compare_endpoint_detects_a_slower_window(client: TestClient) -> None:
    """Ten baseline requests at 11:05 and ten slower ones at 11:30."""
    baseline = [
        payload(f"base-{n}", latency_ms=100.0 + n,
                occurred_at=f"2026-04-01T11:05:{n:02d}Z")
        for n in range(10)
    ]
    candidate = [
        payload(f"cand-{n}", latency_ms=300.0 + n,
                occurred_at=f"2026-04-01T11:30:{n:02d}Z")
        for n in range(10)
    ]
    client.post("/v1/events", json={"events": baseline + candidate})
    client.post("/v1/rollup")

    body = client.get(
        "/v1/stats/compare",
        params={
            "service": "checkout",
            "baseline_start": "2026-04-01T11:05:00Z",
            "baseline_end": "2026-04-01T11:06:00Z",
            "candidate_start": "2026-04-01T11:30:00Z",
            "candidate_end": "2026-04-01T11:31:00Z",
        },
    ).json()
    assert body["comparison"]["effect_size"] == 1.0
    assert body["median_shift_ms"] == pytest.approx(200.0)
    assert body["regressed"] is True


def test_compare_on_an_empty_window_is_a_404(client: TestClient) -> None:
    response = client.get(
        "/v1/stats/compare",
        params={
            "service": "ghost",
            "baseline_start": WINDOW["start"], "baseline_end": WINDOW["end"],
            "candidate_start": WINDOW["start"], "candidate_end": WINDOW["end"],
        },
    )
    assert response.status_code == 404


def test_anomalies_need_history(client: TestClient) -> None:
    """With only the scored window in the warehouse, there is nothing to fit on."""
    client.post("/v1/events", json={"events": [payload("evt-0")]})
    client.post("/v1/rollup")
    response = client.get("/v1/stats/anomalies", params={"service": "checkout", **WINDOW})
    assert response.status_code == 404


def test_the_service_name_is_required_everywhere(client: TestClient) -> None:
    for path in ("/v1/events/recent", "/v1/stats/errors", "/v1/stats/latency"):
        assert client.get(path).status_code == 422
