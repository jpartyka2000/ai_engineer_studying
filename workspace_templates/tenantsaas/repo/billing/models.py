"""Invoices and the usage line items they bill for."""

from django.db import models

from tenants.models import TenantScopedQuerySet


class LineItem(models.Model):
    """A single billable usage event.

    Written continuously by the metering pipeline, then swept up into an invoice at
    the end of each billing period.
    """

    class Kind(models.TextChoices):
        """What the charge is for."""

        SEAT = "seat", "Seat"
        STORAGE = "storage", "Storage"
        API_CALL = "api_call", "API call"
        SUPPORT = "support", "Support"
        CREDIT = "credit", "Credit"

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="line_items")
    project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="line_items",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    description = models.CharField(max_length=200)
    amount_cents = models.IntegerField(help_text="Negative for credits and refunds")
    created_at = models.DateTimeField(db_index=True)

    objects = TenantScopedQuerySet.as_manager()

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["tenant", "created_at"])]

    def __str__(self) -> str:
        return f"{self.kind} {self.amount_cents}c on {self.created_at:%Y-%m-%d}"


class Invoice(models.Model):
    """A finalised bill for one tenant over one billing period."""

    class Status(models.TextChoices):
        """Where the invoice is in its lifecycle."""

        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"
        PAID = "paid", "Paid"
        VOID = "void", "Void"

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="invoices")
    period_start = models.DateField()
    period_end = models.DateField(help_text="Inclusive: the last day the invoice covers")
    subtotal_cents = models.IntegerField(default=0)
    total_cents = models.IntegerField(default=0)
    line_item_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantScopedQuerySet.as_manager()

    class Meta:
        ordering = ["-period_end"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "period_start", "period_end"],
                name="unique_invoice_period_per_tenant",
            )
        ]

    def __str__(self) -> str:
        return f"Invoice {self.tenant.slug} {self.period_start}..{self.period_end}"
