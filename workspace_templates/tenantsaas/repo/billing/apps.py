"""App config for billing."""

from django.apps import AppConfig


class BillingConfig(AppConfig):
    """Invoices and usage metering."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "billing"
