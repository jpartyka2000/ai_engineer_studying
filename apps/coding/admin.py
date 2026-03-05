"""Admin configuration for the coding app."""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import CodingChallenge, CodingResponse, CodingSession


class CodingResponseInline(admin.TabularInline):
    """Inline admin for CodingResponse within CodingSession."""

    model = CodingResponse
    extra = 0
    readonly_fields = [
        "submission_number",
        "overall_score",
        "is_correct",
        "submitted_at",
        "evaluated_at",
    ]
    fields = [
        "submission_number",
        "overall_score",
        "is_correct",
        "submitted_at",
        "evaluated_at",
    ]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CodingChallenge)
class CodingChallengeAdmin(admin.ModelAdmin):
    """Admin interface for CodingChallenge model."""

    list_display = [
        "title",
        "subject",
        "challenge_type",
        "difficulty",
        "language",
        "is_active",
        "created_at",
    ]
    list_filter = ["challenge_type", "difficulty", "language", "subject", "is_active"]
    search_fields = ["title", "description"]
    ordering = ["-created_at"]
    readonly_fields = ["source_hash", "created_at", "updated_at"]

    fieldsets = [
        (None, {"fields": ["subject", "title", "description"]}),
        (
            _("Configuration"),
            {"fields": ["challenge_type", "language", "difficulty", "estimated_time_minutes"]},
        ),
        (
            _("Code"),
            {
                "fields": ["starter_code", "reference_solution"],
                "classes": ["collapse"],
            },
        ),
        (
            _("Evaluation"),
            {
                "fields": ["evaluation_criteria", "expected_output", "hints"],
                "classes": ["collapse"],
            },
        ),
        (
            _("Metadata"),
            {"fields": ["tags", "source", "source_hash", "is_active"]},
        ),
        (
            _("Timestamps"),
            {
                "fields": ["created_at", "updated_at"],
                "classes": ["collapse"],
            },
        ),
    ]


@admin.register(CodingSession)
class CodingSessionAdmin(admin.ModelAdmin):
    """Admin interface for CodingSession model."""

    list_display = [
        "user",
        "challenge_title",
        "difficulty",
        "status",
        "score_display",
        "started_at",
        "completed_at",
    ]
    list_filter = ["status", "difficulty", "subject", "started_at"]
    search_fields = ["user__username", "challenge__title"]
    ordering = ["-started_at"]
    readonly_fields = ["started_at", "submitted_at", "completed_at"]
    inlines = [CodingResponseInline]

    fieldsets = [
        (
            _("User & Challenge"),
            {"fields": ["user", "subject", "challenge"]},
        ),
        (
            _("Configuration"),
            {"fields": ["challenge_type", "difficulty", "language"]},
        ),
        (
            _("Progress"),
            {"fields": ["status", "hints_used"]},
        ),
        (
            _("User Code"),
            {
                "fields": ["user_code"],
                "classes": ["collapse"],
            },
        ),
        (
            _("Timestamps"),
            {"fields": ["started_at", "submitted_at", "completed_at"]},
        ),
    ]

    def challenge_title(self, obj) -> str:
        """Return truncated challenge title."""
        return obj.challenge.title[:50]

    challenge_title.short_description = _("Challenge")

    def score_display(self, obj) -> str:
        """Display the latest score with color coding."""
        response = obj.responses.order_by("-submission_number").first()
        if not response or response.overall_score is None:
            return "-"

        score = response.overall_score
        if score >= 80:
            color = "green"
        elif score >= 60:
            color = "orange"
        else:
            color = "red"

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}/100</span>',
            color,
            score,
        )

    score_display.short_description = _("Score")


@admin.register(CodingResponse)
class CodingResponseAdmin(admin.ModelAdmin):
    """Admin interface for CodingResponse model."""

    list_display = [
        "session_info",
        "submission_number",
        "overall_score",
        "is_correct",
        "submitted_at",
        "evaluated_at",
    ]
    list_filter = ["is_correct", "submitted_at"]
    search_fields = ["session__user__username", "session__challenge__title"]
    ordering = ["-submitted_at"]
    readonly_fields = [
        "session",
        "submitted_code",
        "submission_number",
        "is_correct",
        "overall_score",
        "evaluation_result",
        "correctness_score",
        "style_score",
        "completeness_score",
        "efficiency_score",
        "summary_feedback",
        "detailed_feedback",
        "areas_for_improvement",
        "strengths",
        "submitted_at",
        "evaluated_at",
    ]

    fieldsets = [
        (
            _("Submission"),
            {"fields": ["session", "submission_number", "submitted_code", "submitted_at"]},
        ),
        (
            _("Overall Evaluation"),
            {"fields": ["is_correct", "overall_score", "evaluated_at"]},
        ),
        (
            _("Category Scores"),
            {
                "fields": [
                    "correctness_score",
                    "style_score",
                    "completeness_score",
                    "efficiency_score",
                ]
            },
        ),
        (
            _("Feedback"),
            {
                "fields": [
                    "summary_feedback",
                    "detailed_feedback",
                    "strengths",
                    "areas_for_improvement",
                ]
            },
        ),
        (
            _("Raw Result"),
            {
                "fields": ["evaluation_result"],
                "classes": ["collapse"],
            },
        ),
    ]

    def session_info(self, obj) -> str:
        """Display session user and challenge."""
        return f"{obj.session.user.username} - {obj.session.challenge.title[:30]}"

    session_info.short_description = _("Session")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
