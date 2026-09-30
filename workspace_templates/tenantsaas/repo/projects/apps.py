"""App config for projects."""

from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    """Customer projects."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "projects"
