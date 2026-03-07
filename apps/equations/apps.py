"""App configuration for the equations app."""

from django.apps import AppConfig


class EquationsConfig(AppConfig):
    """Configuration for the equations (Can I Math?) app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.equations"
    verbose_name = "Can I Math?"
