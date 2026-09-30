"""Tests for invoice construction.

The billing period is inclusive at both ends. That is the contract these tests
defend, and it is easy to break: ``created_at`` is a timestamp while the period
bounds are dates, so a direct comparison silently drops the final day.
"""

from datetime import date

import pytest

from billing.models import Invoice, LineItem
from billing.services import build_invoice, compute_totals, line_items_for_period
from tests.conftest import utc

pytestmark = pytest.mark.django_db

MARCH_START = date(2026, 3, 1)
MARCH_END = date(2026, 3, 31)


def test_period_includes_items_on_the_final_day(acme, march_usage):
    """Regression test for INC-2291: invoices were missing the last day's usage.

    An invoice for 1-31 March must bill an item created at 23:30 on the 31st.
    """
    items = line_items_for_period(acme.pk, MARCH_START, MARCH_END)
    descriptions = {item.description for item in items}
    assert "Overage on the last day of the period" in descriptions


def test_period_includes_items_on_the_first_day(acme, march_usage):
    items = line_items_for_period(acme.pk, MARCH_START, MARCH_END)
    assert "Seats, first half" in {item.description for item in items}


def test_period_excludes_items_after_the_period(acme, march_usage):
    items = line_items_for_period(acme.pk, MARCH_START, MARCH_END)
    assert "April seats" not in {item.description for item in items}


def test_period_returns_exactly_the_expected_count(acme, march_usage):
    assert line_items_for_period(acme.pk, MARCH_START, MARCH_END).count() == 4


def test_totals_sum_positive_charges_into_the_subtotal(acme, march_usage):
    totals = compute_totals(acme.pk, MARCH_START, MARCH_END)
    # 6000 + 2500 + 1750, the credit is excluded from the subtotal.
    assert totals.subtotal_cents == 10_250


def test_totals_apply_credits_to_the_total(acme, march_usage):
    totals = compute_totals(acme.pk, MARCH_START, MARCH_END)
    assert totals.total_cents == 9_750


def test_totals_count_every_line_item(acme, march_usage):
    assert compute_totals(acme.pk, MARCH_START, MARCH_END).line_item_count == 4


def test_totals_are_zero_for_a_period_with_no_usage(acme):
    totals = compute_totals(acme.pk, date(2026, 1, 1), date(2026, 1, 31))
    assert totals.subtotal_cents == 0
    assert totals.total_cents == 0
    assert totals.line_item_count == 0


def test_a_single_day_period_bills_that_day(acme, acme_project):
    """A one-day period is the degenerate case of an inclusive range."""
    LineItem.objects.create(
        tenant=acme,
        project=acme_project,
        kind=LineItem.Kind.API_CALL,
        description="Single day",
        amount_cents=300,
        created_at=utc(2026, 5, 10, 8),
    )
    totals = compute_totals(acme.pk, date(2026, 5, 10), date(2026, 5, 10))
    assert totals.line_item_count == 1
    assert totals.total_cents == 300


def test_build_invoice_persists_the_totals(acme, march_usage):
    invoice = build_invoice(acme.pk, MARCH_START, MARCH_END)
    assert invoice.pk is not None
    assert invoice.subtotal_cents == 10_250
    assert invoice.total_cents == 9_750
    assert invoice.line_item_count == 4
    assert invoice.status == Invoice.Status.DRAFT


def test_build_invoice_is_idempotent(acme, march_usage):
    """Re-running the billing job must refresh, not duplicate."""
    first = build_invoice(acme.pk, MARCH_START, MARCH_END)
    second = build_invoice(acme.pk, MARCH_START, MARCH_END)
    assert first.pk == second.pk
    assert Invoice.objects.filter(tenant=acme).count() == 1


def test_invoices_never_mix_tenants(acme, globex, march_usage, acme_project):
    """Globex usage must never appear on an Acme invoice.

    Deliberately asserts only the absence of the other tenant's rows, with no
    exact-total assertion. A total is sensitive to every billing bug there is, so
    checking one here would make this test fail for reasons that have nothing to do
    with isolation -- and a test that fails for a reason other than its name states
    sends whoever is debugging in the wrong direction.
    """
    LineItem.objects.create(
        tenant=globex,
        kind=LineItem.Kind.SEAT,
        description="Globex seats",
        amount_cents=99_999,
        created_at=utc(2026, 3, 10, 9),
    )
    billed = line_items_for_period(acme.pk, MARCH_START, MARCH_END)
    assert "Globex seats" not in {item.description for item in billed}
    assert all(item.tenant_id == acme.pk for item in billed)
