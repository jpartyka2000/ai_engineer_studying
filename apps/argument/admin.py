"""Admin configuration for the argument app."""

from django.contrib import admin

from .models import ArgumentAnalysis, ArgumentMessage, ArgumentSession


class ArgumentMessageInline(admin.TabularInline):
    """Inline display of messages in an argument session."""

    model = ArgumentMessage
    extra = 0
    readonly_fields = ["role", "content", "created_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class ArgumentAnalysisInline(admin.StackedInline):
    """Inline display of analysis for an argument session."""

    model = ArgumentAnalysis
    extra = 0
    readonly_fields = [
        "technical_score",
        "technical_feedback",
        "temperament_score",
        "temperament_feedback",
        "focus_score",
        "focus_feedback",
        "overall_feedback",
        "created_at",
    ]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ArgumentSession)
class ArgumentSessionAdmin(admin.ModelAdmin):
    """Admin configuration for ArgumentSession model."""

    list_display = [
        "user",
        "subject",
        "difficulty",
        "heat_level",
        "status",
        "message_count",
        "started_at",
        "completed_at",
    ]
    list_filter = ["status", "difficulty", "heat_level", "subject"]
    search_fields = ["user__username", "subject__name", "initial_prompt"]
    readonly_fields = ["started_at", "completed_at", "message_count"]
    inlines = [ArgumentMessageInline, ArgumentAnalysisInline]
    ordering = ["-started_at"]

    fieldsets = [
        (
            "Session Info",
            {
                "fields": [
                    "user",
                    "subject",
                    "status",
                ],
            },
        ),
        (
            "Configuration",
            {
                "fields": [
                    "difficulty",
                    "heat_level",
                ],
            },
        ),
        (
            "Content",
            {
                "fields": [
                    "initial_prompt",
                ],
            },
        ),
        (
            "Statistics",
            {
                "fields": [
                    "message_count",
                    "started_at",
                    "completed_at",
                ],
            },
        ),
    ]


@admin.register(ArgumentMessage)
class ArgumentMessageAdmin(admin.ModelAdmin):
    """Admin configuration for ArgumentMessage model."""

    list_display = ["session", "role", "content_preview", "created_at"]
    list_filter = ["role", "session__subject"]
    search_fields = ["content", "session__user__username"]
    readonly_fields = ["created_at"]
    ordering = ["-created_at"]

    def content_preview(self, obj):
        """Return truncated content preview."""
        if len(obj.content) > 100:
            return obj.content[:100] + "..."
        return obj.content

    content_preview.short_description = "Content"


@admin.register(ArgumentAnalysis)
class ArgumentAnalysisAdmin(admin.ModelAdmin):
    """Admin configuration for ArgumentAnalysis model."""

    list_display = [
        "session",
        "technical_score",
        "temperament_score",
        "focus_score",
        "average_score_display",
        "created_at",
    ]
    list_filter = ["session__subject"]
    search_fields = ["session__user__username", "overall_feedback"]
    readonly_fields = ["created_at"]
    ordering = ["-created_at"]

    def average_score_display(self, obj):
        """Display average score."""
        return f"{obj.average_score}/10"

    average_score_display.short_description = "Average"
