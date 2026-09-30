"""Tenant model and the scoped queryset every tenant-owned model should use."""

from django.db import models

from tenants.context import current_tenant_id


class TenantScopedQuerySet(models.QuerySet):
    """A queryset that can restrict itself to the request's current tenant.

    Call :meth:`for_current_tenant` in any code path that serves a tenant request.
    The predicate is applied in SQL rather than filtered in Python, so other
    tenants' rows are never read off disk in the first place.
    """

    def for_tenant(self, tenant_id: int) -> "TenantScopedQuerySet":
        """Restrict to a specific tenant."""
        return self.filter(tenant_id=tenant_id)

    def for_current_tenant(self) -> "TenantScopedQuerySet":
        """Restrict to the tenant resolved by the middleware.

        Raises:
            RuntimeError: If no tenant is in context. Failing closed matters here:
                returning everything would be a cross-tenant data leak.
        """
        tenant_id = current_tenant_id()
        if tenant_id is None:
            raise RuntimeError(
                "No tenant in context. for_current_tenant() must only be called "
                "inside a tenant-scoped request."
            )
        return self.filter(tenant_id=tenant_id)


class Tenant(models.Model):
    """A customer organisation. The isolation boundary for all business data."""

    class Plan(models.TextChoices):
        """Billing plan, which determines the per-seat rate."""

        FREE = "free", "Free"
        TEAM = "team", "Team"
        ENTERPRISE = "enterprise", "Enterprise"

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True)
    api_key = models.CharField(max_length=64, unique=True, db_index=True)
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.TEAM)
    seat_count = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    # Internal tenants may legitimately query across customers for support.
    is_internal = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
