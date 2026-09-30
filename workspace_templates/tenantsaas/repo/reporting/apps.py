"""App config for reporting."""

from django.apps import AppConfig


class ReportingConfig(AppConfig):
    """Usage reporting and revenue analytics."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "reporting"
