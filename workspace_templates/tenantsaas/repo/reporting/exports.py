"""CSV-style exports of a tenant's own data.

Every lookup here is reached from a tenant request, so every lookup must be scoped.
Projects are identified by slug, and slugs are unique **per tenant** rather than
globally -- so a bare ``Project.objects.get(slug=...)`` can return a different
customer's project.
"""

import csv
import io
import logging
from datetime import date

from billing.services import line_items_for_period
from projects.models import Project

logger = logging.getLogger(__name__)

EXPORT_COLUMNS = ["created_at", "kind", "description", "amount_cents"]


class ProjectNotFound(Exception):
    """Raised when a project does not exist for the requesting tenant."""


def resolve_project(tenant_id: int, slug: str) -> Project:
    """Look up one of a tenant's projects by slug.

    Scoped to the tenant in SQL. Slugs are only unique within a tenant, so an
    unscoped lookup would hand back another customer's project -- and everything
    downstream would then faithfully export their data.

    Args:
        tenant_id: The requesting tenant.
        slug: The project slug from the request.

    Returns:
        The matching :class:`~projects.models.Project`.

    Raises:
        ProjectNotFound: If this tenant has no project with that slug. Deliberately
            indistinguishable from "exists but belongs to someone else", so the
            response cannot be used to enumerate other tenants' projects.
    """
    project = Project.objects.filter(tenant_id=tenant_id, slug=slug).first()
    if project is None:
        logger.info("project %r not found for tenant %s", slug, tenant_id)
        raise ProjectNotFound(slug)
    return project


def export_project_line_items(
    tenant_id: int, slug: str, period_start: date, period_end: date
) -> str:
    """Export one project's billable usage as CSV.

    Args:
        tenant_id: The requesting tenant.
        slug: The project slug from the request.
        period_start: First day of the period, inclusive.
        period_end: Last day of the period, inclusive.

    Returns:
        The CSV document as a string, including a header row.

    Raises:
        ProjectNotFound: If the project is not this tenant's.
    """
    project = resolve_project(tenant_id, slug)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_COLUMNS)

    items = line_items_for_period(tenant_id, period_start, period_end).filter(project=project)
    for item in items:
        writer.writerow(
            [
                item.created_at.isoformat(),
                item.kind,
                item.description,
                item.amount_cents,
            ]
        )
    return buffer.getvalue()
