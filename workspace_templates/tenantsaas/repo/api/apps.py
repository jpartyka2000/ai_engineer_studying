"""App config for the API layer."""

from django.apps import AppConfig


class ApiConfig(AppConfig):
    """JSON endpoints."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "api"
