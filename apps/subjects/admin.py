"""Admin configuration for the subjects app."""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Subject


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    """Admin interface for Subject model."""

    list_display = [
        "name",
        "category",
        "supports_visuals",
        "default_question_count",
        "is_active",
        "updated_at",
    ]
    list_filter = ["category", "is_active", "supports_visuals"]
    search_fields = ["name", "description", "category"]
    prepopulated_fields = {"slug": ("name",)}
    ordering = ["category", "name"]

    fieldsets = [
        (
            None,
            {
                "fields": ["name", "slug", "description", "category", "icon"],
            },
        ),
        (
            _("Mode Configuration"),
            {
                "fields": [
                    "supports_visuals",
                    "default_question_count",
                    "difficulty_levels",
                ],
            },
        ),
        (
            _("Status"),
            {
                "fields": ["is_active"],
            },
        ),
    ]

    readonly_fields = ["created_at", "updated_at"]
