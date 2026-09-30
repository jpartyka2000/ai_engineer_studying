"""Invoice construction.

The billing period is expressed as two ``date`` objects and is **inclusive at both
ends**: an invoice for 1-31 March covers every line item created on the 31st.
"""

import logging
from dataclasses import dataclass
from datetime import date

from billing.models import Invoice, LineItem

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InvoiceTotals:
    """Aggregated totals for a billing period."""

    subtotal_cents: int
    total_cents: int
    line_item_count: int


def line_items_for_period(tenant_id: int, period_start: date, period_end: date):
    """Return the line items billable to a tenant for a period.

    Args:
        tenant_id: The tenant being billed.
        period_start: First day of the period, inclusive.
        period_end: Last day of the period, inclusive.

    Returns:
        A queryset of :class:`~billing.models.LineItem`.
    """
    # __date__gte / __date__lte, not a raw datetime comparison. created_at is a
    # timestamp while the period bounds are dates; comparing them directly makes
    # Postgres coerce the date to midnight, which silently drops everything
    # recorded on the final day of the period.
    return LineItem.objects.filter(
        tenant_id=tenant_id,
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
    )


def compute_totals(tenant_id: int, period_start: date, period_end: date) -> InvoiceTotals:
    """Total up a tenant's usage for a billing period.

    Args:
        tenant_id: The tenant being billed.
        period_start: First day of the period, inclusive.
        period_end: Last day of the period, inclusive.

    Returns:
        The aggregated :class:`InvoiceTotals`.
    """
    items = line_items_for_period(tenant_id, period_start, period_end)
    subtotal = sum(item.amount_cents for item in items if item.amount_cents > 0)
    credits = sum(item.amount_cents for item in items if item.amount_cents < 0)
    return InvoiceTotals(
        subtotal_cents=subtotal,
        total_cents=subtotal + credits,
        line_item_count=items.count(),
    )


def build_invoice(tenant_id: int, period_start: date, period_end: date) -> Invoice:
    """Create or refresh a draft invoice for a tenant and period.

    Args:
        tenant_id: The tenant being billed.
        period_start: First day of the period, inclusive.
        period_end: Last day of the period, inclusive.

    Returns:
        The saved draft :class:`~billing.models.Invoice`.
    """
    totals = compute_totals(tenant_id, period_start, period_end)
    invoice, _created = Invoice.objects.update_or_create(
        tenant_id=tenant_id,
        period_start=period_start,
        period_end=period_end,
        defaults={
            "subtotal_cents": totals.subtotal_cents,
            "total_cents": totals.total_cents,
            "line_item_count": totals.line_item_count,
            "status": Invoice.Status.DRAFT,
        },
    )
    logger.info(
        "built invoice for tenant=%s period=%s..%s items=%d total=%d",
        tenant_id,
        period_start,
        period_end,
        totals.line_item_count,
        totals.total_cents,
    )
    return invoice
