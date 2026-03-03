"""Admin configuration for the questions app."""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Question


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    """Admin interface for Question model."""

    list_display = [
        "truncated_question",
        "subject",
        "question_type",
        "difficulty",
        "source",
        "is_active",
        "created_at",
    ]
    list_filter = ["subject", "question_type", "difficulty", "source", "is_active"]
    search_fields = ["question_text", "explanation", "tags"]
    ordering = ["-created_at"]
    readonly_fields = ["source_hash", "created_at", "updated_at"]

    fieldsets = [
        (
            None,
            {
                "fields": ["subject", "question_text", "question_type"],
            },
        ),
        (
            _("Answer"),
            {
                "fields": ["options", "correct_answer", "explanation"],
            },
        ),
        (
            _("Metadata"),
            {
                "fields": ["difficulty", "tags"],
            },
        ),
        (
            _("Source"),
            {
                "fields": ["source", "source_file", "source_hash"],
                "classes": ["collapse"],
            },
        ),
        (
            _("Status"),
            {
                "fields": ["is_active", "created_at", "updated_at"],
            },
        ),
    ]

    def truncated_question(self, obj):
        """Display truncated question text."""
        text = obj.question_text[:80]
        if len(obj.question_text) > 80:
            text += "..."
        return text

    truncated_question.short_description = _("Question")
