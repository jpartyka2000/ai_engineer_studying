"""Usage reporting across a tenant's projects."""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from django.db.models import Count, Sum

from billing.models import LineItem
from billing.services import line_items_for_period
from projects.models import Project

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProjectUsage:
    """Usage totals for a single project over a period."""

    project_id: int
    project_name: str
    line_item_count: int
    total_cents: int


def project_usage_summary(
    tenant_id: int, period_start: date, period_end: date
) -> list[ProjectUsage]:
    """Summarise each of a tenant's projects for a billing period.

    Aggregated in a single query with annotations. Looping over projects and
    issuing one aggregate per project would be an N+1: correct, but it turns one
    round trip into one-per-project, which is what makes this endpoint fall over on
    a tenant with hundreds of projects.

    Args:
        tenant_id: The tenant to report on.
        period_start: First day of the period, inclusive.
        period_end: Last day of the period, inclusive.

    Returns:
        One :class:`ProjectUsage` per project, ordered by name.
    """
    rows = (
        Project.objects.filter(tenant_id=tenant_id)
        .annotate(
            item_count=Count(
                "line_items",
                filter=(
                    models_q_for_period(period_start, period_end)
                ),
            ),
            item_total=Sum(
                "line_items__amount_cents",
                filter=(
                    models_q_for_period(period_start, period_end)
                ),
            ),
        )
        .order_by("name")
        .values("id", "name", "item_count", "item_total")
    )
    return [
        ProjectUsage(
            project_id=row["id"],
            project_name=row["name"],
            line_item_count=row["item_count"] or 0,
            total_cents=row["item_total"] or 0,
        )
        for row in rows
    ]


def models_q_for_period(period_start: date, period_end: date):
    """Build the period predicate used to filter annotated aggregates.

    Kept as a helper so the inclusive-period rule is expressed in exactly one place
    for the annotation path, matching ``billing.services.line_items_for_period``.
    """
    from django.db.models import Q

    return Q(
        line_items__created_at__date__gte=period_start,
        line_items__created_at__date__lte=period_end,
    )


def top_spending_category(tenant_id: int, period_start: date, period_end: date) -> str:
    """Return the line-item kind a tenant spent most on during a period.

    Ties are broken alphabetically by kind. That matters: without an explicit
    tie-break the winner would depend on iteration order, which is not stable across
    interpreter runs once hash randomisation is enabled.

    Args:
        tenant_id: The tenant to report on.
        period_start: First day of the period, inclusive.
        period_end: Last day of the period, inclusive.

    Returns:
        The winning kind, or an empty string when there is no usage.
    """
    totals: dict[str, int] = defaultdict(int)
    for item in line_items_for_period(tenant_id, period_start, period_end):
        if item.amount_cents > 0:
            totals[item.kind] += item.amount_cents

    if not totals:
        return ""

    # Sort by descending total, then ascending kind, so a tie is resolved by name
    # rather than by whatever order the mapping happens to yield.
    ranked = sorted(totals.items(), key=lambda pair: (-pair[1], pair[0]))
    return ranked[0][0]


def tenant_line_item_totals(tenant_id: int) -> dict[str, int]:
    """Return lifetime totals per line-item kind for a tenant.

    Args:
        tenant_id: The tenant to report on.

    Returns:
        Mapping of kind to summed amount in cents, ordered by kind.
    """
    rows = (
        LineItem.objects.filter(tenant_id=tenant_id)
        .values("kind")
        .annotate(total=Sum("amount_cents"))
        .order_by("kind")
    )
    return {row["kind"]: row["total"] or 0 for row in rows}
