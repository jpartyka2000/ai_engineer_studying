"""App config for tenants."""

from django.apps import AppConfig


class TenantsConfig(AppConfig):
    """Tenant isolation primitives."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "tenants"
