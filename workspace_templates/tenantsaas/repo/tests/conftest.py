"""Shared fixtures for the tenantsaas test suite."""

from datetime import datetime, timezone

import pytest
from django.test import Client

from billing.models import LineItem
from projects.models import Project
from tenants.models import Tenant


def utc(year: int, month: int, day: int, hour: int = 12, minute: int = 0) -> datetime:
    """Build an aware UTC datetime, so no test ever writes a naive timestamp."""
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


@pytest.fixture
def acme(db) -> Tenant:
    """A paying customer on the Team plan."""
    return Tenant.objects.create(
        name="Acme Corp", slug="acme", api_key="key-acme-0001", plan=Tenant.Plan.TEAM, seat_count=12
    )


@pytest.fixture
def globex(db) -> Tenant:
    """A second, unrelated customer. Used to prove isolation."""
    return Tenant.objects.create(
        name="Globex", slug="globex", api_key="key-globex-0002", plan=Tenant.Plan.FREE, seat_count=3
    )


@pytest.fixture
def acme_project(acme) -> Project:
    return Project.objects.create(tenant=acme, name="Website", slug="website")


@pytest.fixture
def client_for():
    """Return a factory building a client authenticated as a given tenant."""

    def _build(tenant: Tenant) -> Client:
        return Client(headers={"x-api-key": tenant.api_key})

    return _build


@pytest.fixture
def march_usage(acme, acme_project):
    """Line items spread across March 2026, including one on the final day.

    The item on the 31st is the interesting one: an invoice for 1-31 March is
    inclusive at both ends, so it must be billed.
    """
    items = [
        LineItem.objects.create(
            tenant=acme,
            project=acme_project,
            kind=LineItem.Kind.SEAT,
            description="Seats, first half",
            amount_cents=6000,
            created_at=utc(2026, 3, 1, 9),
        ),
        LineItem.objects.create(
            tenant=acme,
            project=acme_project,
            kind=LineItem.Kind.STORAGE,
            description="Storage",
            amount_cents=2500,
            created_at=utc(2026, 3, 15, 14),
        ),
        LineItem.objects.create(
            tenant=acme,
            project=acme_project,
            kind=LineItem.Kind.API_CALL,
            description="Overage on the last day of the period",
            amount_cents=1750,
            created_at=utc(2026, 3, 31, 23, 30),
        ),
        LineItem.objects.create(
            tenant=acme,
            project=acme_project,
            kind=LineItem.Kind.CREDIT,
            description="Goodwill credit",
            amount_cents=-500,
            created_at=utc(2026, 3, 20, 10),
        ),
        # Outside the period: belongs on April's invoice, not March's.
        LineItem.objects.create(
            tenant=acme,
            project=acme_project,
            kind=LineItem.Kind.SEAT,
            description="April seats",
            amount_cents=6000,
            created_at=utc(2026, 4, 1, 9),
        ),
    ]
    return items
