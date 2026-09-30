"""Django app configuration for workspace."""

from django.apps import AppConfig


class WorkspaceConfig(AppConfig):
    """Configuration for the Work With Existing Codebase app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.workspace"
    verbose_name = "Work With Existing Codebase"
