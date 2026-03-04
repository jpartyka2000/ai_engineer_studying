"""
Visuals mode models.

This module contains models for the Visuals study mode, where users explore
step-by-step visual explanations of concepts through interactive diagrams.
"""

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class VisualTopic(models.Model):
    """
    Represents a visual topic with step-by-step diagram content.

    Visual topics contain a sequence of steps, each with diagram data
    and explanatory text. Supports multiple rendering types including
    Mermaid.js, D3.js, and static images.
    """

    class RenderingType(models.TextChoices):
        MERMAID = "mermaid", _("Mermaid.js (Flowcharts/Trees)")
        D3 = "d3", _("D3.js (Custom Interactive)")
        STATIC = "static", _("Static Image/SVG")
        CODE = "code", _("Code Evolution")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PUBLISHED = "published", _("Published")
        ARCHIVED = "archived", _("Archived")

    # Relationships
    subject = models.ForeignKey(
        "subjects.Subject",
        on_delete=models.CASCADE,
        related_name="visual_topics",
        help_text=_("The subject this visual belongs to"),
    )

    # Core fields
    title = models.CharField(
        max_length=200,
        help_text=_("Display title for the visual topic"),
    )
    slug = models.SlugField(
        max_length=200,
        help_text=_("URL-safe identifier"),
    )
    description = models.TextField(
        help_text=_("Brief description shown in topic picker"),
    )

    # Visual configuration
    rendering_type = models.CharField(
        max_length=20,
        choices=RenderingType.choices,
        default=RenderingType.MERMAID,
        help_text=_("How to render the diagram"),
    )
    steps = models.JSONField(
        default=list,
        help_text=_(
            "Array of step objects: [{step_number, title, explanation, diagram_data}, ...]"
        ),
    )

    # Metadata
    difficulty = models.CharField(
        max_length=20,
        default="intermediate",
        help_text=_("Difficulty level of the concept"),
    )
    estimated_time_minutes = models.PositiveIntegerField(
        default=5,
        help_text=_("Estimated time to complete the visual"),
    )
    tags = models.JSONField(
        default=list,
        help_text=_("Related topic tags"),
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )

    # Source tracking
    source = models.CharField(
        max_length=50,
        default="manual",
        help_text=_("How this visual was created (manual, claude_api)"),
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["subject", "title"]
        verbose_name = _("Visual Topic")
        verbose_name_plural = _("Visual Topics")
        unique_together = [["subject", "slug"]]
        indexes = [
            models.Index(fields=["subject", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.subject.name} - {self.title}"

    def get_absolute_url(self) -> str:
        """Get the URL for this visual topic viewer."""
        return reverse(
            "visuals:viewer",
            kwargs={"subject_slug": self.subject.slug, "topic_slug": self.slug},
        )

    @property
    def step_count(self) -> int:
        """Return the number of steps in this visual."""
        return len(self.steps)

    def get_step(self, step_number: int) -> dict | None:
        """
        Get a specific step by number.

        Args:
            step_number: Zero-indexed step number.

        Returns:
            dict: Step data or None if out of range.
        """
        if 0 <= step_number < len(self.steps):
            return self.steps[step_number]
        return None

    def get_system_message(self) -> str:
        """
        Generate system message for Claude explanations.

        Returns:
            str: The system message to prime Claude's responses.
        """
        return (
            f"You are an expert instructor explaining {self.subject.name} concepts "
            f"through visual diagrams. The user is viewing a step-by-step visual "
            f"explanation titled '{self.title}'. "
            f"Provide clear, detailed explanations that complement the visual. "
            f"Use markdown formatting and include code examples where helpful. "
            f"Be pedagogical and connect concepts to practical applications."
        )


class VisualSession(models.Model):
    """
    Tracks user viewing sessions for visual topics.

    This model records user progress through visual topics, enabling
    "continue where you left off" functionality and completion tracking.
    """

    # Relationships
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="visual_sessions",
        help_text=_("The user viewing this visual"),
    )
    visual_topic = models.ForeignKey(
        VisualTopic,
        on_delete=models.CASCADE,
        related_name="sessions",
        help_text=_("The visual topic being viewed"),
    )

    # Progress tracking
    current_step = models.PositiveIntegerField(
        default=0,
        help_text=_("Current step index (0-indexed)"),
    )
    max_step_reached = models.PositiveIntegerField(
        default=0,
        help_text=_("Highest step index the user has viewed"),
    )
    completed = models.BooleanField(
        default=False,
        help_text=_("Whether the user has viewed all steps"),
    )

    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
    last_viewed_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the user completed all steps"),
    )

    class Meta:
        ordering = ["-last_viewed_at"]
        verbose_name = _("Visual Session")
        verbose_name_plural = _("Visual Sessions")
        unique_together = [["user", "visual_topic"]]
        indexes = [
            models.Index(fields=["user", "completed"]),
        ]

    def __str__(self) -> str:
        status = "completed" if self.completed else f"step {self.current_step + 1}"
        return f"{self.user.username} - {self.visual_topic.title} ({status})"

    def update_progress(self, step_number: int) -> None:
        """
        Update session progress when user views a step.

        Args:
            step_number: The step index the user is viewing.
        """
        self.current_step = step_number
        self.max_step_reached = max(self.max_step_reached, step_number)
        self.last_viewed_at = timezone.now()

        # Check if completed (viewed all steps)
        if step_number >= self.visual_topic.step_count - 1:
            if not self.completed:
                self.completed = True
                self.completed_at = timezone.now()

        self.save()

    @property
    def progress_percentage(self) -> int:
        """Calculate completion percentage based on max step reached."""
        total_steps = self.visual_topic.step_count
        if total_steps == 0:
            return 0
        return int((self.max_step_reached + 1) / total_steps * 100)
