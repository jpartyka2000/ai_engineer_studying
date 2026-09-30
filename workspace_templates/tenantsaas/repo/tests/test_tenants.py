"""Tenant isolation tests.

These assert the boundary that matters most in a multi-tenant system: one
customer's request must never be able to read another customer's rows.
"""

import pytest

from projects.models import Project
from tenants.context import current_tenant_id, tenant_context

pytestmark = [pytest.mark.django_db, pytest.mark.security]


def test_for_current_tenant_scopes_to_the_active_tenant(acme, globex, acme_project):
    Project.objects.create(tenant=globex, name="Secret", slug="secret")

    with tenant_context(acme.pk):
        visible = list(Project.objects.for_current_tenant())

    assert [project.slug for project in visible] == ["website"]


def test_for_current_tenant_fails_closed_without_a_tenant(acme, acme_project):
    """Returning everything would be a cross-tenant leak, so this must raise."""
    with pytest.raises(RuntimeError, match="No tenant in context"):
        list(Project.objects.for_current_tenant())


def test_for_tenant_scopes_explicitly(acme, globex, acme_project):
    Project.objects.create(tenant=globex, name="Secret", slug="secret")
    assert Project.objects.for_tenant(globex.pk).count() == 1
    assert Project.objects.for_tenant(acme.pk).count() == 1


def test_middleware_clears_the_context_after_a_request(acme, acme_project, client_for):
    """A leaked ContextVar would let the next request inherit this tenant."""
    client_for(acme).get("/projects")
    assert current_tenant_id() is None


def test_tenant_context_restores_the_previous_value(acme, globex):
    with tenant_context(acme.pk):
        assert current_tenant_id() == acme.pk
        with tenant_context(globex.pk):
            assert current_tenant_id() == globex.pk
        assert current_tenant_id() == acme.pk
    assert current_tenant_id() is None


def test_project_slugs_are_unique_per_tenant_not_globally(acme, globex):
    """Two customers must be able to use the same project name."""
    Project.objects.create(tenant=acme, name="Website", slug="website")
    Project.objects.create(tenant=globex, name="Website", slug="website")
    assert Project.objects.count() == 2
