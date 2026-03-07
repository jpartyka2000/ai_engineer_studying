"""Admin configuration for the equations app."""

from django.contrib import admin
from django.utils.html import format_html

from .models import MathAnswer, MathProblem, MathSession, MathSessionProblem


class MathSessionProblemInline(admin.TabularInline):
    """Inline for viewing problems in a session."""

    model = MathSessionProblem
    extra = 0
    readonly_fields = ["problem", "order"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class MathAnswerInline(admin.TabularInline):
    """Inline for viewing answers in a session."""

    model = MathAnswer
    extra = 0
    readonly_fields = [
        "problem",
        "user_answer_latex",
        "is_correct",
        "partial_credit",
        "hints_used",
        "answered_at",
    ]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(MathProblem)
class MathProblemAdmin(admin.ModelAdmin):
    """Admin for MathProblem model."""

    list_display = [
        "topic",
        "subject",
        "problem_type",
        "difficulty",
        "source",
        "is_active",
        "created_at",
    ]
    list_filter = [
        "problem_type",
        "difficulty",
        "subject",
        "source",
        "is_active",
    ]
    search_fields = ["topic", "problem_text", "problem_latex"]
    readonly_fields = ["created_at", "updated_at"]
    ordering = ["-created_at"]

    fieldsets = (
        (None, {
            "fields": (
                "subject",
                "topic",
                "problem_type",
                "difficulty",
                "is_active",
            )
        }),
        ("Problem Content", {
            "fields": (
                "problem_text",
                "problem_latex",
                "blank_placeholder",
            )
        }),
        ("Answer", {
            "fields": (
                "correct_answer_latex",
                "acceptable_alternatives",
            )
        }),
        ("Multiple Choice", {
            "fields": ("options", "correct_option"),
            "classes": ("collapse",),
        }),
        ("Help & Metadata", {
            "fields": (
                "explanation",
                "hints",
                "tags",
                "source",
            )
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


@admin.register(MathSession)
class MathSessionAdmin(admin.ModelAdmin):
    """Admin for MathSession model."""

    list_display = [
        "id",
        "user",
        "subject",
        "status",
        "score_display",
        "accuracy_display",
        "started_at",
    ]
    list_filter = ["status", "subject", "difficulty"]
    search_fields = ["user__username", "user__email"]
    readonly_fields = [
        "started_at",
        "completed_at",
        "progress_percentage",
        "accuracy_percentage",
    ]
    ordering = ["-started_at"]
    inlines = [MathSessionProblemInline, MathAnswerInline]

    fieldsets = (
        (None, {
            "fields": ("user", "subject", "status")
        }),
        ("Configuration", {
            "fields": (
                "difficulty",
                "problem_types",
                "topic_filter",
            )
        }),
        ("Progress", {
            "fields": (
                "current_problem_index",
                "total_problems",
                "progress_percentage",
            )
        }),
        ("Score", {
            "fields": (
                "score",
                "total_points",
                "accuracy_percentage",
            )
        }),
        ("Timestamps", {
            "fields": ("started_at", "completed_at"),
        }),
    )

    @admin.display(description="Score")
    def score_display(self, obj):
        return f"{obj.score}/{obj.total_problems}"

    @admin.display(description="Accuracy")
    def accuracy_display(self, obj):
        accuracy = obj.accuracy_percentage
        if accuracy >= 80:
            color = "green"
        elif accuracy >= 60:
            color = "orange"
        else:
            color = "red"
        return format_html(
            '<span style="color: {};">{:.0f}%</span>',
            color,
            accuracy,
        )


@admin.register(MathAnswer)
class MathAnswerAdmin(admin.ModelAdmin):
    """Admin for MathAnswer model."""

    list_display = [
        "id",
        "session",
        "problem_topic",
        "is_correct",
        "partial_credit_display",
        "hints_used",
        "answered_at",
    ]
    list_filter = ["is_correct", "session__subject"]
    search_fields = [
        "session__user__username",
        "problem__topic",
    ]
    readonly_fields = ["answered_at", "evaluated_at"]
    ordering = ["-answered_at"]

    fieldsets = (
        (None, {
            "fields": ("session", "problem")
        }),
        ("User's Answer", {
            "fields": (
                "user_answer_latex",
                "selected_option",
            )
        }),
        ("Evaluation", {
            "fields": (
                "is_correct",
                "partial_credit",
                "feedback",
                "mathematical_errors",
            )
        }),
        ("Metadata", {
            "fields": (
                "hints_used",
                "time_taken_seconds",
                "answered_at",
                "evaluated_at",
            )
        }),
    )

    @admin.display(description="Topic")
    def problem_topic(self, obj):
        return obj.problem.topic

    @admin.display(description="Credit")
    def partial_credit_display(self, obj):
        if obj.partial_credit is None:
            return "-"
        credit = obj.partial_credit * 100
        if credit >= 100:
            color = "green"
        elif credit > 0:
            color = "orange"
        else:
            color = "red"
        return format_html(
            '<span style="color: {};">{:.0f}%</span>',
            color,
            credit,
        )
