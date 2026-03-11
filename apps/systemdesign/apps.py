"""Django app configuration for systemdesign."""

from django.apps import AppConfig


class SystemdesignConfig(AppConfig):
    """Configuration for the System Design app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.systemdesign"
    verbose_name = "System Design"
