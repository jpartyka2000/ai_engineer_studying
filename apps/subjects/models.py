"""Models for the subjects app."""

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class Subject(models.Model):
    """
    Represents a study subject area for AI/ML interview preparation.

    Subjects are the top-level organizational unit. Users select a subject
    and then choose a study mode (Exam, Lightning, Q&A, or Visuals).
    """

    # Core fields
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text=_("Display name for the subject (e.g., 'LightGBM')"),
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text=_("URL-safe identifier for the subject"),
    )
    description = models.TextField(
        blank=True,
        help_text=_("Short description shown in the subject picker"),
    )
    category = models.CharField(
        max_length=50,
        db_index=True,
        help_text=_("Grouping label (e.g., 'ML Frameworks', 'Python Core')"),
    )
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text=_("Optional icon identifier for the UI (e.g., icon class name)"),
    )

    # Mode configuration
    supports_visuals = models.BooleanField(
        default=False,
        help_text=_("Whether Visuals mode is available for this subject"),
    )
    coding_language = models.CharField(
        max_length=20,
        blank=True,
        help_text=_(
            "If this subject has its own coding language (e.g., 'git', 'sql', 'shell'), "
            "specify it here. Leave blank for Python-only subjects like LightGBM."
        ),
    )
    default_question_count = models.PositiveIntegerField(
        default=10,
        help_text=_("Default number of questions for Exam mode"),
    )
    difficulty_levels = models.JSONField(
        default=list,
        help_text=_(
            "Available difficulty tiers (e.g., ['beginner', 'intermediate', 'advanced'])"
        ),
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text=_("Soft-disable toggle for the subject"),
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "name"]
        verbose_name = _("Subject")
        verbose_name_plural = _("Subjects")

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        """Set default difficulty levels if not provided."""
        if not self.difficulty_levels:
            self.difficulty_levels = ["beginner", "intermediate", "advanced", "interview"]
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        """Return the URL for the subject detail page."""
        return reverse("subjects:detail", kwargs={"slug": self.slug})

    @property
    def available_modes(self) -> list[str]:
        """Return list of available study modes for this subject."""
        modes = ["exam", "lightning", "qanda"]
        if self.supports_visuals:
            modes.append("visuals")
        return modes
