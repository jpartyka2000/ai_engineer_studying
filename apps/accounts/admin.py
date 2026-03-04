"""Admin configuration for the accounts app."""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import StudyStreak, UserProgress


@admin.register(UserProgress)
class UserProgressAdmin(admin.ModelAdmin):
    """Admin interface for UserProgress model."""

    list_display = [
        "user",
        "subject",
        "total_sessions_display",
        "accuracy_display",
        "last_studied_at",
    ]
    list_filter = ["subject", "last_studied_at"]
    search_fields = ["user__username", "subject__name"]
    ordering = ["-last_studied_at"]
    readonly_fields = ["last_studied_at"]

    fieldsets = [
        (
            None,
            {
                "fields": ["user", "subject", "last_studied_at"],
            },
        ),
        (
            _("Exam Statistics"),
            {
                "fields": ["exam_sessions", "exam_correct", "exam_total"],
            },
        ),
        (
            _("Lightning Statistics"),
            {
                "fields": [
                    "lightning_sessions",
                    "lightning_correct",
                    "lightning_total",
                    "lightning_best_streak",
                ],
            },
        ),
        (
            _("Q&A Statistics"),
            {
                "fields": ["qa_sessions"],
            },
        ),
    ]

    def total_sessions_display(self, obj):
        """Display total sessions count."""
        return obj.total_sessions

    total_sessions_display.short_description = _("Total Sessions")

    def accuracy_display(self, obj):
        """Display accuracy as percentage."""
        return f"{obj.accuracy_percentage}%"

    accuracy_display.short_description = _("Accuracy")


@admin.register(StudyStreak)
class StudyStreakAdmin(admin.ModelAdmin):
    """Admin interface for StudyStreak model."""

    list_display = [
        "user",
        "current_streak",
        "longest_streak",
        "last_activity_date",
        "is_active_today_display",
    ]
    list_filter = ["last_activity_date"]
    search_fields = ["user__username"]
    ordering = ["-current_streak"]
    readonly_fields = ["last_activity_date"]

    def is_active_today_display(self, obj):
        """Display if user has studied today."""
        return obj.is_active_today

    is_active_today_display.short_description = _("Active Today")
    is_active_today_display.boolean = True
