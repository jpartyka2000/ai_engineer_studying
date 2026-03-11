"""Admin configuration for the System Design app."""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    DiagramAnalysis,
    SystemDesignChallenge,
    SystemDesignMessage,
    SystemDesignScore,
    SystemDesignSession,
)


class SystemDesignMessageInline(admin.TabularInline):
    """Inline display of messages in a session."""

    model = SystemDesignMessage
    extra = 0
    readonly_fields = ("role", "content", "message_type", "token_count_estimate", "created_at")
    can_delete = False
    ordering = ["created_at"]

    def has_add_permission(self, request, obj=None):
        return False


class DiagramAnalysisInline(admin.TabularInline):
    """Inline display of diagram analyses in a session."""

    model = DiagramAnalysis
    extra = 0
    readonly_fields = (
        "analysis_type",
        "identified_components",
        "strengths",
        "concerns",
        "preliminary_scores",
        "created_at",
    )
    can_delete = False
    ordering = ["-created_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SystemDesignChallenge)
class SystemDesignChallengeAdmin(admin.ModelAdmin):
    """Admin interface for system design challenges."""

    list_display = (
        "title",
        "difficulty",
        "time_limit_display",
        "source",
        "is_active",
        "session_count",
    )
    list_filter = ("difficulty", "source", "is_active")
    search_fields = ("title", "description", "tags")
    prepopulated_fields = {"slug": ("title",)}
    ordering = ["difficulty", "title"]

    fieldsets = (
        (None, {
            "fields": ("title", "slug", "description", "difficulty", "is_active"),
        }),
        ("Requirements", {
            "fields": (
                "functional_requirements",
                "non_functional_requirements",
                "constraints",
            ),
            "classes": ("collapse",),
        }),
        ("Reference Solution", {
            "fields": (
                "reference_solution_description",
                "reference_components",
            ),
            "classes": ("collapse",),
        }),
        ("Configuration", {
            "fields": (
                "time_limit_seconds",
                "evaluation_criteria",
                "source",
                "tags",
            ),
            "classes": ("collapse",),
        }),
    )

    def time_limit_display(self, obj):
        """Display time limit in minutes."""
        minutes = obj.time_limit_seconds // 60
        return f"{minutes} min"
    time_limit_display.short_description = "Time Limit"

    def session_count(self, obj):
        """Count of sessions for this challenge."""
        return obj.sessions.count()
    session_count.short_description = "Sessions"


@admin.register(SystemDesignSession)
class SystemDesignSessionAdmin(admin.ModelAdmin):
    """Admin interface for system design sessions."""

    list_display = (
        "id",
        "user",
        "challenge_display",
        "difficulty",
        "status",
        "time_display",
        "score_display",
        "started_at",
    )
    list_filter = ("status", "difficulty", "started_at")
    search_fields = ("user__username", "challenge__title")
    readonly_fields = (
        "user",
        "challenge",
        "difficulty",
        "time_limit_seconds",
        "started_at",
        "submitted_at",
        "completed_at",
        "time_remaining_display",
    )
    ordering = ["-started_at"]

    inlines = [SystemDesignMessageInline, DiagramAnalysisInline]

    fieldsets = (
        (None, {
            "fields": ("user", "challenge", "status", "difficulty"),
        }),
        ("Timing", {
            "fields": (
                "time_limit_seconds",
                "started_at",
                "submitted_at",
                "completed_at",
                "time_remaining_display",
            ),
        }),
        ("Surprise Challenge Data", {
            "fields": ("surprise_challenge_data",),
            "classes": ("collapse",),
        }),
        ("Canvas State", {
            "fields": ("canvas_state",),
            "classes": ("collapse",),
        }),
    )

    def challenge_display(self, obj):
        """Display challenge title or 'Surprise' for generated challenges."""
        return obj.effective_challenge_title
    challenge_display.short_description = "Challenge"

    def time_display(self, obj):
        """Display time remaining or elapsed."""
        if obj.status == SystemDesignSession.Status.IN_PROGRESS:
            remaining = obj.time_remaining_seconds
            mins, secs = divmod(remaining, 60)
            return f"{mins}:{secs:02d} remaining"
        elif obj.completed_at and obj.started_at:
            elapsed = (obj.completed_at - obj.started_at).total_seconds()
            mins, secs = divmod(int(elapsed), 60)
            return f"{mins}:{secs:02d} used"
        return "-"
    time_display.short_description = "Time"

    def time_remaining_display(self, obj):
        """Display formatted time remaining."""
        remaining = obj.time_remaining_seconds
        mins, secs = divmod(remaining, 60)
        return f"{mins}:{secs:02d}"
    time_remaining_display.short_description = "Time Remaining"

    def score_display(self, obj):
        """Display overall score if available."""
        try:
            score = obj.final_score
            return f"{score.overall_score}/100"
        except SystemDesignScore.DoesNotExist:
            return "-"
    score_display.short_description = "Score"

    def has_add_permission(self, request):
        return False


@admin.register(SystemDesignScore)
class SystemDesignScoreAdmin(admin.ModelAdmin):
    """Admin interface for system design scores."""

    list_display = (
        "session",
        "overall_score",
        "scalability_score",
        "reliability_score",
        "performance_score",
        "cost_efficiency_score",
        "communication_score",
        "created_at",
    )
    list_filter = ("created_at",)
    search_fields = ("session__user__username", "session__challenge__title")
    readonly_fields = (
        "session",
        "scalability_score",
        "reliability_score",
        "performance_score",
        "cost_efficiency_score",
        "communication_score",
        "overall_score",
        "created_at",
    )
    ordering = ["-created_at"]

    fieldsets = (
        (None, {
            "fields": ("session", "overall_score", "created_at"),
        }),
        ("Individual Scores", {
            "fields": (
                "scalability_score",
                "reliability_score",
                "performance_score",
                "cost_efficiency_score",
                "communication_score",
            ),
        }),
        ("Feedback", {
            "fields": (
                "strengths_narrative",
                "weaknesses_narrative",
                "design_coherence_feedback",
                "comparison_to_reference",
            ),
        }),
        ("Details", {
            "fields": ("detailed_feedback", "scoring_model_used"),
            "classes": ("collapse",),
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SystemDesignMessage)
class SystemDesignMessageAdmin(admin.ModelAdmin):
    """Admin interface for individual messages (for debugging)."""

    list_display = ("id", "session", "role", "message_type", "content_preview", "created_at")
    list_filter = ("role", "message_type", "created_at")
    search_fields = ("content", "session__user__username")
    readonly_fields = ("session", "role", "content", "message_type", "token_count_estimate", "created_at")
    ordering = ["-created_at"]

    def content_preview(self, obj):
        """Show truncated content."""
        if len(obj.content) > 100:
            return obj.content[:100] + "..."
        return obj.content
    content_preview.short_description = "Content"

    def has_add_permission(self, request):
        return False


@admin.register(DiagramAnalysis)
class DiagramAnalysisAdmin(admin.ModelAdmin):
    """Admin interface for diagram analyses (for debugging)."""

    list_display = (
        "id",
        "session",
        "analysis_type",
        "component_count",
        "preliminary_scores_display",
        "created_at",
    )
    list_filter = ("analysis_type", "created_at")
    search_fields = ("session__user__username",)
    readonly_fields = (
        "session",
        "analysis_type",
        "identified_components",
        "identified_connections",
        "strengths",
        "concerns",
        "suggestions",
        "overall_impression",
        "preliminary_scores",
        "created_at",
    )
    ordering = ["-created_at"]

    def component_count(self, obj):
        """Count identified components."""
        return len(obj.identified_components)
    component_count.short_description = "Components"

    def preliminary_scores_display(self, obj):
        """Display preliminary scores summary."""
        if not obj.preliminary_scores:
            return "-"
        scores = obj.preliminary_scores
        parts = []
        for key in ["scalability", "reliability", "performance", "cost"]:
            if key in scores:
                parts.append(f"{key[:4]}:{scores[key]}")
        return ", ".join(parts) if parts else "-"
    preliminary_scores_display.short_description = "Scores"

    def has_add_permission(self, request):
        return False
