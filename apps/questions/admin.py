"""Admin configuration for the questions app."""

import json
from datetime import datetime
from pathlib import Path

from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _

from .models import Question, StudyMaterial


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
    actions = ["export_to_json"]

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

    @admin.action(description="Export selected questions to JSON")
    def export_to_json(self, request, queryset):
        """Export selected questions to a JSON file."""
        output_dir = Path("questions")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Group questions by subject
        questions_by_subject = {}
        for q in queryset:
            subject_slug = q.subject.slug
            if subject_slug not in questions_by_subject:
                questions_by_subject[subject_slug] = {
                    "subject_name": q.subject.name,
                    "questions": [],
                }
            questions_by_subject[subject_slug]["questions"].append({
                "question_text": q.question_text,
                "question_type": q.question_type,
                "options": q.options,
                "correct_answer": q.correct_answer,
                "explanation": q.explanation,
                "difficulty": q.difficulty,
                "tags": q.tags,
                "source": q.source,
                "is_active": q.is_active,
            })

        # Export each subject to its own file
        exported_count = 0
        for subject_slug, data in questions_by_subject.items():
            output_data = {
                "metadata": {
                    "subject_slug": subject_slug,
                    "subject_name": data["subject_name"],
                    "exported_at": datetime.now().isoformat(),
                    "question_count": len(data["questions"]),
                    "format_version": "1.0",
                },
                "questions": data["questions"],
            }

            output_path = output_dir / f"{subject_slug}_export.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)

            exported_count += len(data["questions"])

        messages.success(
            request,
            f"Exported {exported_count} question(s) from {len(questions_by_subject)} subject(s) to {output_dir}/",
        )


@admin.register(StudyMaterial)
class StudyMaterialAdmin(admin.ModelAdmin):
    """Admin interface for StudyMaterial model."""

    list_display = [
        "title",
        "subject",
        "token_estimate",
        "questions_generated",
        "is_active",
        "created_at",
    ]
    list_filter = ["subject", "is_active", "created_at"]
    search_fields = ["title", "content", "source_file"]
    ordering = ["-created_at"]
    readonly_fields = ["content_hash", "token_estimate", "created_at", "updated_at"]

    fieldsets = [
        (
            None,
            {
                "fields": ["subject", "title", "is_active"],
            },
        ),
        (
            _("Content"),
            {
                "fields": ["content", "source_file"],
            },
        ),
        (
            _("Statistics"),
            {
                "fields": ["token_estimate", "questions_generated"],
            },
        ),
        (
            _("Metadata"),
            {
                "fields": ["content_hash", "created_at", "updated_at"],
                "classes": ["collapse"],
            },
        ),
    ]
