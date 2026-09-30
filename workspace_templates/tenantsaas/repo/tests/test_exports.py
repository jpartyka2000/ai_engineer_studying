"""Tests for project exports, with the tenant boundary as the focus.

Project slugs are unique per tenant rather than globally, so two customers can both
own a project called "website". That is exactly the condition under which an unscoped
lookup by slug silently returns the wrong customer's data.
"""

from datetime import date

import pytest

from billing.models import LineItem
from projects.models import Project
from reporting.exports import ProjectNotFound, export_project_line_items, resolve_project
from tests.conftest import utc

pytestmark = [pytest.mark.django_db, pytest.mark.security]

MARCH_START = date(2026, 3, 1)
MARCH_END = date(2026, 3, 31)


@pytest.fixture
def shared_slug(acme, globex):
    """Both tenants own a project with the same slug, each with its own data."""
    acme_project = Project.objects.create(tenant=acme, name="Website", slug="website")
    globex_project = Project.objects.create(tenant=globex, name="Website", slug="website")

    LineItem.objects.create(
        tenant=acme, project=acme_project, kind=LineItem.Kind.SEAT,
        description="ACME SEATS", amount_cents=1_000, created_at=utc(2026, 3, 5, 9),
    )
    LineItem.objects.create(
        tenant=globex, project=globex_project, kind=LineItem.Kind.SEAT,
        description="GLOBEX CONFIDENTIAL", amount_cents=77_777,
        created_at=utc(2026, 3, 6, 9),
    )
    return acme_project, globex_project


# ---------------------------------------------------------------------------
# resolve_project
# ---------------------------------------------------------------------------


def test_resolve_returns_the_callers_own_project(acme, shared_slug):
    acme_project, _ = shared_slug
    assert resolve_project(acme.pk, "website").pk == acme_project.pk


def test_resolve_never_returns_another_tenants_project(globex, shared_slug):
    """The core isolation assertion.

    Globex asking for 'website' must get Globex's project, never Acme's, even though
    both exist under the same slug.
    """
    _, globex_project = shared_slug
    assert resolve_project(globex.pk, "website").pk == globex_project.pk


def test_resolve_raises_for_a_slug_owned_by_someone_else(acme, globex):
    """Must be indistinguishable from 'does not exist'.

    A different error for 'exists but is not yours' would let a caller enumerate
    other tenants' project slugs.
    """
    Project.objects.create(tenant=globex, name="Secret Project", slug="secret-project")
    with pytest.raises(ProjectNotFound):
        resolve_project(acme.pk, "secret-project")


def test_resolve_raises_for_a_slug_that_exists_nowhere(acme):
    with pytest.raises(ProjectNotFound):
        resolve_project(acme.pk, "no-such-project")


# ---------------------------------------------------------------------------
# export_project_line_items
# ---------------------------------------------------------------------------


def test_export_includes_a_header_row(acme, shared_slug):
    csv_text = export_project_line_items(acme.pk, "website", MARCH_START, MARCH_END)
    assert csv_text.splitlines()[0] == "created_at,kind,description,amount_cents"


def test_export_contains_the_callers_own_rows(acme, shared_slug):
    csv_text = export_project_line_items(acme.pk, "website", MARCH_START, MARCH_END)
    assert "ACME SEATS" in csv_text


def test_export_never_leaks_another_tenants_rows(acme, shared_slug):
    """The assertion that proves the leak.

    Acme exporting 'website' must not contain a single byte of Globex's data.
    """
    csv_text = export_project_line_items(acme.pk, "website", MARCH_START, MARCH_END)
    assert "GLOBEX CONFIDENTIAL" not in csv_text
    assert "77777" not in csv_text


def test_export_for_each_tenant_is_disjoint(acme, globex, shared_slug):
    acme_csv = export_project_line_items(acme.pk, "website", MARCH_START, MARCH_END)
    globex_csv = export_project_line_items(globex.pk, "website", MARCH_START, MARCH_END)
    assert "ACME SEATS" in acme_csv and "ACME SEATS" not in globex_csv
    assert "GLOBEX CONFIDENTIAL" in globex_csv and "GLOBEX CONFIDENTIAL" not in acme_csv


def test_export_refuses_a_project_the_caller_does_not_own(acme, globex):
    Project.objects.create(tenant=globex, name="Secret", slug="secret")
    with pytest.raises(ProjectNotFound):
        export_project_line_items(acme.pk, "secret", MARCH_START, MARCH_END)


def test_export_respects_the_billing_period(acme, shared_slug):
    csv_text = export_project_line_items(acme.pk, "website", date(2026, 1, 1), date(2026, 1, 31))
    # Header only.
    assert len(csv_text.strip().splitlines()) == 1
