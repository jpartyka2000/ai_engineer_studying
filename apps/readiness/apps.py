"""Readiness app configuration."""

from django.apps import AppConfig


class ReadinessConfig(AppConfig):
    """Configuration for the readiness app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.readiness"
    verbose_name = "Interview Readiness"
