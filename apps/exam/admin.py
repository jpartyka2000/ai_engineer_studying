"""Admin configuration for the exam app."""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import ExamAnswer, ExamSession


class ExamAnswerInline(admin.TabularInline):
    """Inline admin for ExamAnswer within ExamSession."""

    model = ExamAnswer
    extra = 0
    readonly_fields = [
        "question",
        "user_answer",
        "is_correct",
        "is_flagged",
        "answered_at",
    ]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ExamSession)
class ExamSessionAdmin(admin.ModelAdmin):
    """Admin interface for ExamSession model."""

    list_display = [
        "user",
        "subject",
        "difficulty",
        "score_display",
        "status",
        "started_at",
    ]
    list_filter = ["status", "difficulty", "subject", "started_at"]
    search_fields = ["user__username", "subject__name"]
    ordering = ["-started_at"]
    readonly_fields = ["started_at", "completed_at", "score", "total_answered"]
    inlines = [ExamAnswerInline]

    fieldsets = [
        (
            None,
            {
                "fields": ["user", "subject", "difficulty", "question_count"],
            },
        ),
        (
            _("Progress"),
            {
                "fields": [
                    "status",
                    "current_question_index",
                    "score",
                    "total_answered",
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
        return f"{obj.score}/{obj.total_answered} ({obj.score_percentage}%)"

    score_display.short_description = _("Score")


@admin.register(ExamAnswer)
class ExamAnswerAdmin(admin.ModelAdmin):
    """Admin interface for ExamAnswer model."""

    list_display = [
        "session",
        "question_preview",
        "user_answer",
        "is_correct",
        "is_flagged",
        "answered_at",
    ]
    list_filter = ["is_correct", "is_flagged", "session__subject"]
    search_fields = ["question__question_text", "session__user__username"]
    ordering = ["session", "order"]
    readonly_fields = ["answered_at"]

    def question_preview(self, obj):
        """Display truncated question text."""
        text = obj.question.question_text[:50]
        if len(obj.question.question_text) > 50:
            text += "..."
        return text

    question_preview.short_description = _("Question")
