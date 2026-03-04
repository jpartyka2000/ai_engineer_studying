"""Admin configuration for the visuals app."""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import VisualSession, VisualTopic


@admin.register(VisualTopic)
class VisualTopicAdmin(admin.ModelAdmin):
    """Admin interface for VisualTopic model."""

    list_display = [
        "title",
        "subject",
        "rendering_type",
        "step_count_display",
        "difficulty",
        "status",
        "updated_at",
    ]
    list_filter = ["status", "rendering_type", "difficulty", "subject"]
    search_fields = ["title", "description", "subject__name"]
    prepopulated_fields = {"slug": ("title",)}
    ordering = ["subject", "title"]
    readonly_fields = ["created_at", "updated_at", "step_preview"]

    fieldsets = [
        (
            None,
            {
                "fields": ["subject", "title", "slug", "description"],
            },
        ),
        (
            _("Visual Configuration"),
            {
                "fields": ["rendering_type", "steps", "step_preview"],
                "classes": ["wide"],
            },
        ),
        (
            _("Metadata"),
            {
                "fields": [
                    "difficulty",
                    "estimated_time_minutes",
                    "tags",
                    "status",
                    "source",
                ],
            },
        ),
        (
            _("Timestamps"),
            {
                "fields": ["created_at", "updated_at"],
                "classes": ["collapse"],
            },
        ),
    ]

    def step_count_display(self, obj):
        """Display number of steps."""
        count = obj.step_count
        return f"{count} step{'s' if count != 1 else ''}"

    step_count_display.short_description = _("Steps")

    def step_preview(self, obj):
        """Show preview of step titles."""
        if not obj.steps:
            return format_html('<span class="text-gray-400">No steps defined</span>')

        titles = []
        for i, step in enumerate(obj.steps[:5]):
            title = step.get("title", "Untitled")
            titles.append(f"{i + 1}. {title}")

        if len(obj.steps) > 5:
            titles.append(f"... and {len(obj.steps) - 5} more")

        return format_html("<br>".join(titles))

    step_preview.short_description = _("Step Preview")


@admin.register(VisualSession)
class VisualSessionAdmin(admin.ModelAdmin):
    """Admin interface for VisualSession model."""

    list_display = [
        "user",
        "visual_topic",
        "progress_display",
        "completed",
        "started_at",
        "last_viewed_at",
    ]
    list_filter = ["completed", "visual_topic__subject", "started_at"]
    search_fields = [
        "user__username",
        "visual_topic__title",
        "visual_topic__subject__name",
    ]
    ordering = ["-last_viewed_at"]
    readonly_fields = [
        "started_at",
        "last_viewed_at",
        "completed_at",
        "progress_percentage",
    ]

    fieldsets = [
        (
            None,
            {
                "fields": ["user", "visual_topic"],
            },
        ),
        (
            _("Progress"),
            {
                "fields": [
                    "current_step",
                    "max_step_reached",
                    "progress_percentage",
                    "completed",
                ],
            },
        ),
        (
            _("Timestamps"),
            {
                "fields": ["started_at", "last_viewed_at", "completed_at"],
            },
        ),
    ]

    def progress_display(self, obj):
        """Display progress as percentage bar."""
        percentage = obj.progress_percentage
        color = "green" if obj.completed else "purple"
        return format_html(
            '<div style="width:100px; background:#e5e7eb; border-radius:4px;">'
            '<div style="width:{}%; background:{}; height:8px; border-radius:4px;"></div>'
            "</div>"
            '<span style="font-size:12px; color:#666;">{:.0f}%</span>',
            percentage,
            color,
            percentage,
        )

    progress_display.short_description = _("Progress")

    def progress_percentage(self, obj):
        """Display progress percentage."""
        return f"{obj.progress_percentage}%"

    progress_percentage.short_description = _("Progress %")
