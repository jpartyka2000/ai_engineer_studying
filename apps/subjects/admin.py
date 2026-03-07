"""Admin configuration for the subjects app."""

from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.questions.models import Question

from .models import Subject


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    """Admin interface for Subject model."""

    list_display = [
        "name",
        "category",
        "question_count",
        "coding_language",
        "supports_visuals",
        "supports_math",
        "is_active",
        "generate_questions_link",
    ]
    list_filter = ["category", "is_active", "supports_visuals", "supports_math", "coding_language"]
    search_fields = ["name", "description", "category"]
    prepopulated_fields = {"slug": ("name",)}
    ordering = ["category", "name"]
    actions = [
        "analyze_coverage",
        "generate_10_questions",
        "generate_until_complete",
        "export_questions_json",
    ]

    def question_count(self, obj):
        """Show the number of questions for this subject."""
        count = Question.objects.filter(subject=obj, is_active=True).count()
        return count

    question_count.short_description = "Questions"

    def generate_questions_link(self, obj):
        """Link to the question generation page."""
        url = reverse("admin:subjects_subject_generate_questions", args=[obj.pk])
        return format_html('<a href="{}">Generate Questions</a>', url)

    generate_questions_link.short_description = "Actions"

    def get_urls(self):
        """Add custom URLs for question generation."""
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:subject_id>/generate-questions/",
                self.admin_site.admin_view(self.generate_questions_view),
                name="subjects_subject_generate_questions",
            ),
        ]
        return custom_urls + urls

    def generate_questions_view(self, request, subject_id):
        """Custom view for generating interview questions."""
        subject = Subject.objects.get(pk=subject_id)

        if request.method == "POST":
            from apps.questions.services.interview_coverage import (
                get_interview_coverage_service,
            )

            service = get_interview_coverage_service()

            mode = request.POST.get("mode", "specific")
            difficulty = request.POST.get("difficulty") or None

            try:
                if mode == "complete":
                    saved = service.generate_gap_filling_questions(
                        subject=subject,
                        fill_until_complete=True,
                        difficulty=difficulty,
                    )
                    messages.success(
                        request,
                        f"Generated {len(saved)} questions to achieve full coverage.",
                    )
                else:
                    num = int(request.POST.get("num_questions", 10))
                    saved = service.generate_gap_filling_questions(
                        subject=subject,
                        num_questions=num,
                        difficulty=difficulty,
                    )
                    messages.success(request, f"Generated {len(saved)} questions.")

            except Exception as e:
                messages.error(request, f"Failed to generate questions: {e}")

            return redirect("admin:subjects_subject_changelist")

        # GET: Show the form
        from apps.questions.services.interview_coverage import (
            get_interview_coverage_service,
        )

        service = get_interview_coverage_service()

        try:
            coverage = service.analyze_coverage(subject)
            interview_topics = service.get_interview_topics(subject)
        except Exception as e:
            coverage = None
            interview_topics = None
            messages.warning(request, f"Could not analyze coverage: {e}")

        existing = service.get_existing_coverage(subject)

        context = {
            **self.admin_site.each_context(request),
            "subject": subject,
            "coverage": coverage,
            "interview_topics": interview_topics,
            "existing": existing,
            "title": f"Generate Questions: {subject.name}",
            "opts": self.model._meta,
        }

        return render(request, "admin/subjects/generate_questions.html", context)

    @admin.action(description="Analyze question coverage")
    def analyze_coverage(self, request, queryset):
        """Analyze coverage for selected subjects."""
        from apps.questions.services.interview_coverage import (
            get_interview_coverage_service,
        )

        service = get_interview_coverage_service()

        for subject in queryset:
            try:
                coverage = service.analyze_coverage(subject)
                messages.info(
                    request,
                    f"{subject.name}: {len(coverage.covered_topics)} covered, "
                    f"{len(coverage.partially_covered_topics)} partial, "
                    f"{len(coverage.missing_topics)} missing topics",
                )
            except Exception as e:
                messages.error(request, f"{subject.name}: Analysis failed - {e}")

    @admin.action(description="Generate 10 interview questions")
    def generate_10_questions(self, request, queryset):
        """Generate 10 questions for selected subjects."""
        from apps.questions.services.interview_coverage import (
            get_interview_coverage_service,
        )

        service = get_interview_coverage_service()

        for subject in queryset:
            try:
                saved = service.generate_gap_filling_questions(
                    subject=subject,
                    num_questions=10,
                )
                messages.success(
                    request, f"{subject.name}: Generated {len(saved)} questions"
                )
            except Exception as e:
                messages.error(request, f"{subject.name}: Generation failed - {e}")

    @admin.action(description="Generate until full coverage")
    def generate_until_complete(self, request, queryset):
        """Generate questions until full coverage for selected subjects."""
        from apps.questions.services.interview_coverage import (
            get_interview_coverage_service,
        )

        service = get_interview_coverage_service()

        for subject in queryset:
            try:
                saved = service.generate_gap_filling_questions(
                    subject=subject,
                    fill_until_complete=True,
                )
                messages.success(
                    request,
                    f"{subject.name}: Generated {len(saved)} questions for full coverage",
                )
            except Exception as e:
                messages.error(request, f"{subject.name}: Generation failed - {e}")

    @admin.action(description="Export questions to JSON")
    def export_questions_json(self, request, queryset):
        """Export questions for selected subjects to JSON files."""
        import json
        from datetime import datetime
        from pathlib import Path

        output_dir = Path("questions")
        output_dir.mkdir(parents=True, exist_ok=True)

        exported_count = 0
        skipped_count = 0

        for subject in queryset:
            questions = Question.objects.filter(subject=subject, is_active=True)

            # Skip subjects with no questions
            if questions.count() == 0:
                skipped_count += 1
                continue

            data = {
                "metadata": {
                    "subject_slug": subject.slug,
                    "subject_name": subject.name,
                    "exported_at": datetime.now().isoformat(),
                    "question_count": questions.count(),
                    "format_version": "1.0",
                },
                "questions": [],
            }

            for q in questions.order_by("difficulty", "created_at"):
                data["questions"].append({
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

            output_path = output_dir / f"{subject.slug}.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            exported_count += 1

        if exported_count > 0:
            messages.success(
                request,
                f"Exported {exported_count} subject(s) to {output_dir}/",
            )
        if skipped_count > 0:
            messages.info(
                request,
                f"Skipped {skipped_count} subject(s) with no questions",
            )

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
                    "supports_math",
                    "default_question_count",
                    "difficulty_levels",
                    "coding_language",
                ],
                "description": _(
                    "Set 'Coding language' to enable that language option in coding challenges. "
                    "Options: git, sql, shell (for Linux/Bash). Leave blank for Python-only subjects."
                ),
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
