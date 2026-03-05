"""Admin configuration for the readiness app."""

from django.contrib import admin

from apps.readiness.models import ReadinessSnapshot


@admin.register(ReadinessSnapshot)
class ReadinessSnapshotAdmin(admin.ModelAdmin):
    """Admin for ReadinessSnapshot model."""

    list_display = [
        "user",
        "role_level",
        "overall_score",
        "is_ready",
        "sessions_in_period",
        "created_at",
    ]
    list_filter = ["role_level", "is_ready", "created_at"]
    search_fields = ["user__username", "user__email"]
    readonly_fields = [
        "user",
        "role_level",
        "overall_score",
        "is_ready",
        "coding_score",
        "exam_score",
        "argument_score",
        "lightning_score",
        "category_scores",
        "category_coverage",
        "difficulty_scores",
        "assessment_period_start",
        "assessment_period_end",
        "sessions_in_period",
        "recommendations",
        "created_at",
    ]
    ordering = ["-created_at"]

    def has_add_permission(self, request) -> bool:
        """Snapshots are created programmatically, not manually."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Snapshots are immutable."""
        return False
