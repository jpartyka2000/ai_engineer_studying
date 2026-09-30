"""Contract tests for the JSON API."""

import json

import pytest

pytestmark = pytest.mark.django_db


def test_healthz_needs_no_api_key(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_a_missing_api_key_is_rejected(client):
    assert client.get("/projects").status_code == 401


def test_an_unknown_api_key_is_rejected(client):
    response = client.get("/projects", headers={"x-api-key": "key-does-not-exist"})
    assert response.status_code == 403


def test_an_inactive_tenant_is_rejected(acme, client_for):
    acme.is_active = False
    acme.save(update_fields=["is_active"])
    assert client_for(acme).get("/projects").status_code == 403


def test_projects_lists_only_the_callers_projects(acme, globex, acme_project, client_for):
    from projects.models import Project

    Project.objects.create(tenant=globex, name="Secret", slug="secret")

    payload = client_for(acme).get("/projects").json()
    slugs = {project["slug"] for project in payload["projects"]}
    assert slugs == {"website"}


def test_usage_summary_returns_period_totals(acme, march_usage, client_for):
    response = client_for(acme).get(
        "/usage", {"period_start": "2026-03-01", "period_end": "2026-03-31"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["line_item_count"] == 4
    assert body["total_cents"] == 9_750


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"period_start": "2026-03-01"},
        {"period_start": "not-a-date", "period_end": "2026-03-31"},
        {"period_start": "2026-03-31", "period_end": "2026-03-01"},
    ],
)
def test_usage_summary_rejects_bad_periods(acme, client_for, params):
    assert client_for(acme).get("/usage", params).status_code == 400


def test_create_invoice_returns_201_with_the_invoice(acme, march_usage, client_for):
    response = client_for(acme).post(
        "/invoices/create",
        data=json.dumps({"period_start": "2026-03-01", "period_end": "2026-03-31"}),
        content_type="application/json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["total_cents"] == 9_750
    assert body["status"] == "draft"


def test_create_invoice_rejects_a_non_json_body(acme, client_for):
    response = client_for(acme).post(
        "/invoices/create", data="not json", content_type="application/json"
    )
    assert response.status_code == 400


def test_create_invoice_rejects_a_get(acme, client_for):
    assert client_for(acme).get("/invoices/create").status_code == 405


def test_invoices_lists_only_the_callers_invoices(acme, globex, march_usage, client_for):
    from billing.services import build_invoice
    from datetime import date

    build_invoice(acme.pk, date(2026, 3, 1), date(2026, 3, 31))
    build_invoice(globex.pk, date(2026, 3, 1), date(2026, 3, 31))

    payload = client_for(acme).get("/invoices").json()
    assert len(payload["invoices"]) == 1
