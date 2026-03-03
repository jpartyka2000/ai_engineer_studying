"""Admin configuration for the lightning app."""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import LightningAnswer, LightningSession


class LightningAnswerInline(admin.TabularInline):
    """Inline admin for LightningAnswer within LightningSession."""

    model = LightningAnswer
    extra = 0
    readonly_fields = [
        "question",
        "user_answer",
        "is_correct",
        "answered_at",
        "response_time_ms",
    ]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(LightningSession)
class LightningSessionAdmin(admin.ModelAdmin):
    """Admin interface for LightningSession model."""

    list_display = [
        "user",
        "subject",
        "difficulty",
        "score_display",
        "best_streak",
        "status",
        "time_limit_display",
        "started_at",
    ]
    list_filter = [
        "status",
        "difficulty",
        "subject",
        "time_limit_seconds",
        "started_at",
    ]
    search_fields = ["user__username", "subject__name"]
    ordering = ["-started_at"]
    readonly_fields = [
        "started_at",
        "completed_at",
        "questions_answered",
        "questions_correct",
        "current_streak",
        "best_streak",
    ]
    inlines = [LightningAnswerInline]

    fieldsets = [
        (
            None,
            {
                "fields": ["user", "subject", "difficulty", "time_limit_seconds"],
            },
        ),
        (
            _("Progress"),
            {
                "fields": [
                    "status",
                    "questions_answered",
                    "questions_correct",
                    "current_streak",
                    "best_streak",
                ],
            },
        ),
        (
            _("Timestamps"),
            {
                "fields": ["started_at", "completed_at"],
            },
        ),
    ]

    def score_display(self, obj):
        """Display score as fraction and percentage."""
        return f"{obj.questions_correct}/{obj.questions_answered} ({obj.accuracy_percentage}%)"

    score_display.short_description = _("Score")

    def time_limit_display(self, obj):
        """Display time limit in a friendly format."""
        minutes = obj.time_limit_seconds // 60
        if minutes == 1:
            return "1 min"
        return f"{minutes} mins"

    time_limit_display.short_description = _("Time Limit")


@admin.register(LightningAnswer)
class LightningAnswerAdmin(admin.ModelAdmin):
    """Admin interface for LightningAnswer model."""

    list_display = [
        "session",
        "question_preview",
        "user_answer",
        "is_correct",
        "response_time_display",
        "answered_at",
    ]
    list_filter = ["is_correct", "session__subject"]
    search_fields = ["question__question_text", "session__user__username"]
    ordering = ["-answered_at"]
    readonly_fields = ["answered_at"]

    def question_preview(self, obj):
        """Display truncated question text."""
        text = obj.question.question_text[:50]
        if len(obj.question.question_text) > 50:
            text += "..."
        return text

    question_preview.short_description = _("Question")

    def response_time_display(self, obj):
        """Display response time in a friendly format."""
        if obj.response_time_ms < 1000:
            return f"{obj.response_time_ms}ms"
        return f"{obj.response_time_ms / 1000:.1f}s"

    response_time_display.short_description = _("Response Time")
