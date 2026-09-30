"""JSON endpoints for the billing platform.

Plain Django views returning ``JsonResponse``. There is no DRF here deliberately --
the dependency set is kept thin so the exercise image builds fast.
"""

import json
from datetime import date

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from billing.models import Invoice
from billing.services import build_invoice, compute_totals
from projects.models import Project
from reporting.exports import ProjectNotFound, export_project_line_items
from reporting.services import project_usage_summary, top_spending_category


@require_GET
def healthz(request: HttpRequest) -> JsonResponse:
    """Liveness probe. Deliberately requires no tenant."""
    return JsonResponse({"status": "ok"})


@require_GET
def list_projects(request: HttpRequest) -> JsonResponse:
    """List the calling tenant's projects."""
    projects = Project.objects.for_current_tenant().values(
        "id", "name", "slug", "status", "storage_bytes"
    )
    return JsonResponse({"projects": list(projects)})


def _parse_period(payload: dict) -> tuple[date, date]:
    """Parse inclusive period bounds from a request payload.

    Raises:
        ValueError: If either bound is missing or not an ISO date.
    """
    try:
        start = date.fromisoformat(payload["period_start"])
        end = date.fromisoformat(payload["period_end"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("period_start and period_end must be ISO dates (YYYY-MM-DD)") from exc
    if end < start:
        raise ValueError("period_end must not be before period_start")
    return start, end


@require_GET
def usage_summary(request: HttpRequest) -> JsonResponse:
    """Return usage totals for a billing period without persisting an invoice."""
    try:
        start, end = _parse_period(request.GET)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    totals = compute_totals(request.tenant.pk, start, end)
    return JsonResponse(
        {
            "tenant": request.tenant.slug,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "subtotal_cents": totals.subtotal_cents,
            "total_cents": totals.total_cents,
            "line_item_count": totals.line_item_count,
        }
    )


@require_POST
def create_invoice(request: HttpRequest) -> JsonResponse:
    """Build a draft invoice for the calling tenant."""
    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"error": "Request body must be JSON"}, status=400)

    try:
        start, end = _parse_period(payload)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    invoice = build_invoice(request.tenant.pk, start, end)
    return JsonResponse(
        {
            "id": invoice.pk,
            "tenant": request.tenant.slug,
            "period_start": invoice.period_start.isoformat(),
            "period_end": invoice.period_end.isoformat(),
            "subtotal_cents": invoice.subtotal_cents,
            "total_cents": invoice.total_cents,
            "line_item_count": invoice.line_item_count,
            "status": invoice.status,
        },
        status=201,
    )


@require_GET
def list_invoices(request: HttpRequest) -> JsonResponse:
    """List the calling tenant's invoices."""
    invoices = Invoice.objects.for_current_tenant().values(
        "id", "period_start", "period_end", "total_cents", "line_item_count", "status"
    )
    return JsonResponse({"invoices": list(invoices)}, json_dumps_params={"default": str})


@require_GET
def usage_by_project(request: HttpRequest) -> JsonResponse:
    """Per-project usage totals for a billing period."""
    try:
        start, end = _parse_period(request.GET)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    rows = project_usage_summary(request.tenant.pk, start, end)
    return JsonResponse(
        {
            "projects": [
                {
                    "id": row.project_id,
                    "name": row.project_name,
                    "line_item_count": row.line_item_count,
                    "total_cents": row.total_cents,
                }
                for row in rows
            ],
            "top_category": top_spending_category(request.tenant.pk, start, end),
        }
    )


@require_GET
def export_project(request: HttpRequest, slug: str) -> HttpResponse:
    """Export one project's usage as CSV."""
    try:
        start, end = _parse_period(request.GET)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    try:
        body = export_project_line_items(request.tenant.pk, slug, start, end)
    except ProjectNotFound:
        return JsonResponse({"error": "No such project"}, status=404)

    response = HttpResponse(body, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{slug}.csv"'
    return response
