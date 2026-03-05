"""Models for the readiness app."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class RoleLevel(models.TextChoices):
    """Target interview role levels."""

    ENTRY = "entry", _("Entry-level")
    SENIOR = "senior", _("Senior")
    PRINCIPAL = "principal", _("Principal")


class ReadinessSnapshot(models.Model):
    """
    Stores a point-in-time readiness assessment for historical tracking.

    Calculated on demand but cached here for performance and trend analysis.
    """

    # Relationships
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="readiness_snapshots",
        help_text=_("The user this assessment belongs to"),
    )

    # Target role level at time of calculation
    role_level = models.CharField(
        max_length=20,
        choices=RoleLevel.choices,
        default=RoleLevel.ENTRY,
        help_text=_("Target role level for this assessment"),
    )

    # Overall scores
    overall_score = models.FloatField(
        help_text=_("Weighted composite score (0-100)"),
    )
    is_ready = models.BooleanField(
        help_text=_("Meets threshold for target role"),
    )

    # Mode scores (weighted)
    coding_score = models.FloatField(
        null=True,
        help_text=_("Coding mode score (0-100)"),
    )
    exam_score = models.FloatField(
        null=True,
        help_text=_("Exam mode score (0-100)"),
    )
    argument_score = models.FloatField(
        null=True,
        help_text=_("Argument mode score (0-100)"),
    )
    lightning_score = models.FloatField(
        null=True,
        help_text=_("Lightning mode score (0-100)"),
    )

    # Category coverage (JSON)
    category_scores = models.JSONField(
        default=dict,
        help_text=_("Score per required category: {category_name: score}"),
    )
    category_coverage = models.JSONField(
        default=dict,
        help_text=_(
            "Coverage per category: {category_name: {subjects_attempted, "
            "subjects_required, is_covered}}"
        ),
    )

    # Difficulty breakdown
    difficulty_scores = models.JSONField(
        default=dict,
        help_text=_("{difficulty_level: {correct, total, accuracy}}"),
    )

    # Assessment metadata
    assessment_period_start = models.DateField(
        help_text=_("Start of the assessment period"),
    )
    assessment_period_end = models.DateField(
        help_text=_("End of the assessment period"),
    )
    sessions_in_period = models.PositiveIntegerField(
        help_text=_("Number of sessions completed in the assessment period"),
    )

    # Recommendations (generated at snapshot time)
    recommendations = models.JSONField(
        default=list,
        help_text=_("List of study recommendations"),
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Readiness Snapshot")
        verbose_name_plural = _("Readiness Snapshots")
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "role_level", "-created_at"]),
        ]

    def __str__(self) -> str:
        ready_str = "Ready" if self.is_ready else "Not Ready"
        return (
            f"{self.user.username} - {self.get_role_level_display()} - "
            f"{ready_str} ({self.overall_score:.0f}%)"
        )
