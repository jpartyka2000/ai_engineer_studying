"""Tests for usage reporting.

Two properties matter here beyond correctness: the summary must not scale its query
count with the number of projects, and the top-category tie-break must be stable
across interpreter runs.
"""

from datetime import date

import pytest
from django.test.utils import CaptureQueriesContext, override_settings
from django.db import connection

from billing.models import LineItem
from projects.models import Project
from reporting.services import (
    project_usage_summary,
    tenant_line_item_totals,
    top_spending_category,
)
from tests.conftest import utc

pytestmark = pytest.mark.django_db

MARCH_START = date(2026, 3, 1)
MARCH_END = date(2026, 3, 31)


@pytest.fixture
def many_projects(acme):
    """Twelve projects, each with three March line items."""
    projects = []
    for index in range(12):
        project = Project.objects.create(
            tenant=acme, name=f"Project {index:02d}", slug=f"project-{index:02d}"
        )
        for n in range(3):
            LineItem.objects.create(
                tenant=acme,
                project=project,
                kind=LineItem.Kind.API_CALL,
                description=f"usage {index}-{n}",
                amount_cents=100,
                created_at=utc(2026, 3, 5 + n, 10),
            )
        projects.append(project)
    return projects


# ---------------------------------------------------------------------------
# project_usage_summary
# ---------------------------------------------------------------------------


def test_summary_reports_every_project(acme, many_projects):
    rows = project_usage_summary(acme.pk, MARCH_START, MARCH_END)
    assert len(rows) == 12


def test_summary_totals_are_correct(acme, many_projects):
    rows = project_usage_summary(acme.pk, MARCH_START, MARCH_END)
    assert all(row.line_item_count == 3 for row in rows)
    assert all(row.total_cents == 300 for row in rows)


def test_summary_is_ordered_by_project_name(acme, many_projects):
    rows = project_usage_summary(acme.pk, MARCH_START, MARCH_END)
    assert [row.project_name for row in rows] == sorted(row.project_name for row in rows)


def test_summary_includes_a_project_with_no_usage(acme, many_projects):
    """A quiet project must appear with zeroes, not vanish from the report."""
    Project.objects.create(tenant=acme, name="Quiet", slug="quiet")
    rows = project_usage_summary(acme.pk, MARCH_START, MARCH_END)
    quiet = next(row for row in rows if row.project_name == "Quiet")
    assert quiet.line_item_count == 0
    assert quiet.total_cents == 0


def test_summary_excludes_other_tenants(acme, globex, many_projects):
    Project.objects.create(tenant=globex, name="Globex Secret", slug="secret")
    rows = project_usage_summary(acme.pk, MARCH_START, MARCH_END)
    assert "Globex Secret" not in {row.project_name for row in rows}


def test_summary_respects_the_period(acme, many_projects):
    rows = project_usage_summary(acme.pk, date(2026, 1, 1), date(2026, 1, 31))
    assert all(row.line_item_count == 0 for row in rows)


@pytest.mark.perf
def test_summary_does_not_scale_queries_with_project_count(acme, many_projects):
    """The N+1 guard.

    A constant, small number of queries regardless of how many projects a tenant
    has. Asserting a ceiling rather than an exact count leaves room for harmless
    changes while still failing loudly on a per-project loop.
    """
    with override_settings(DEBUG=True), CaptureQueriesContext(connection) as captured:
        project_usage_summary(acme.pk, MARCH_START, MARCH_END)

    assert len(captured) <= 3, (
        f"{len(captured)} queries for 12 projects: this looks like one query per "
        "project rather than a single aggregate"
    )


@pytest.mark.perf
def test_summary_query_count_is_flat_as_projects_grow(acme, many_projects):
    """Doubling the projects must not change the query count."""
    with override_settings(DEBUG=True), CaptureQueriesContext(connection) as before:
        project_usage_summary(acme.pk, MARCH_START, MARCH_END)

    for index in range(12, 24):
        Project.objects.create(tenant=acme, name=f"Project {index:02d}", slug=f"project-{index:02d}")

    with override_settings(DEBUG=True), CaptureQueriesContext(connection) as after:
        project_usage_summary(acme.pk, MARCH_START, MARCH_END)

    assert len(after) == len(before)


# ---------------------------------------------------------------------------
# top_spending_category
# ---------------------------------------------------------------------------


@pytest.fixture
def tied_categories(acme, acme_project):
    """Two kinds with identical totals, so the tie-break is what decides."""
    for kind in (LineItem.Kind.STORAGE, LineItem.Kind.API_CALL):
        LineItem.objects.create(
            tenant=acme,
            project=acme_project,
            kind=kind,
            description=f"{kind} usage",
            amount_cents=5_000,
            created_at=utc(2026, 3, 10, 9),
        )
    return acme


def test_top_category_picks_the_largest(acme, acme_project):
    LineItem.objects.create(
        tenant=acme, project=acme_project, kind=LineItem.Kind.SEAT,
        description="seats", amount_cents=9_000, created_at=utc(2026, 3, 2, 9),
    )
    LineItem.objects.create(
        tenant=acme, project=acme_project, kind=LineItem.Kind.STORAGE,
        description="storage", amount_cents=1_000, created_at=utc(2026, 3, 3, 9),
    )
    assert top_spending_category(acme.pk, MARCH_START, MARCH_END) == LineItem.Kind.SEAT


def test_top_category_breaks_ties_alphabetically(tied_categories, acme):
    """Must be stable across runs.

    'api_call' sorts before 'storage', so an exact tie resolves to api_call every
    time. Without an explicit tie-break this would depend on iteration order, which
    is not stable once hash randomisation is on -- and CI enables it.
    """
    assert top_spending_category(acme.pk, MARCH_START, MARCH_END) == LineItem.Kind.API_CALL


def test_top_category_is_deterministic_across_repeated_calls(tied_categories, acme):
    results = {top_spending_category(acme.pk, MARCH_START, MARCH_END) for _ in range(25)}
    assert len(results) == 1, f"non-deterministic result: {results}"


def test_top_category_ignores_credits(acme, acme_project):
    """A large refund must not win 'most spent on'."""
    LineItem.objects.create(
        tenant=acme, project=acme_project, kind=LineItem.Kind.CREDIT,
        description="refund", amount_cents=-90_000, created_at=utc(2026, 3, 4, 9),
    )
    LineItem.objects.create(
        tenant=acme, project=acme_project, kind=LineItem.Kind.SEAT,
        description="seats", amount_cents=500, created_at=utc(2026, 3, 5, 9),
    )
    assert top_spending_category(acme.pk, MARCH_START, MARCH_END) == LineItem.Kind.SEAT


def test_top_category_with_no_usage_is_empty(acme):
    assert top_spending_category(acme.pk, MARCH_START, MARCH_END) == ""


# ---------------------------------------------------------------------------
# tenant_line_item_totals
# ---------------------------------------------------------------------------


def test_lifetime_totals_group_by_kind(acme, march_usage):
    totals = tenant_line_item_totals(acme.pk)
    assert totals[LineItem.Kind.SEAT] == 12_000  # 6000 in March + 6000 in April
    assert totals[LineItem.Kind.CREDIT] == -500


def test_lifetime_totals_exclude_other_tenants(acme, globex, march_usage):
    LineItem.objects.create(
        tenant=globex, kind=LineItem.Kind.SEAT, description="globex",
        amount_cents=99_999, created_at=utc(2026, 3, 1, 9),
    )
    assert tenant_line_item_totals(acme.pk)[LineItem.Kind.SEAT] == 12_000
