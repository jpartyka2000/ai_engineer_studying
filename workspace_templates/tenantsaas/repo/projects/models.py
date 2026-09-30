"""Projects, the unit of work customers organise their usage around."""

from django.db import models

from tenants.models import TenantScopedQuerySet


class Project(models.Model):
    """A customer project. Owned by exactly one tenant."""

    class Status(models.TextChoices):
        """Lifecycle of a project."""

        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        ARCHIVED = "archived", "Archived"

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    storage_bytes = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantScopedQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "slug"], name="unique_project_slug_per_tenant")
        ]

    def __str__(self) -> str:
        return f"{self.tenant.slug}/{self.slug}"
