"""
Argument mode models.

This module contains models for the Argument study mode,
where users engage in technical debates with an AI-simulated
argumentative software engineer.
"""

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class ArgumentSession(models.Model):
    """
    Represents an argument session between user and AI opponent.

    Users select a subject, difficulty, and heat level, then engage
    in a back-and-forth debate with an AI challenger. Sessions end
    when the user chooses to end the argument, triggering an analysis.
    """

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", _("In Progress")
        COMPLETED = "completed", _("Completed")
        ABANDONED = "abandoned", _("Abandoned")

    class HeatLevel(models.TextChoices):
        FRIEND = "friend", _("Friendly Debate")
        COLLEAGUE = "colleague", _("Professional Disagreement")
        JERK = "jerk", _("Aggressive Challenger")

    # Relationships
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="argument_sessions",
        help_text=_("The user participating in this argument"),
    )
    subject = models.ForeignKey(
        "subjects.Subject",
        on_delete=models.CASCADE,
        related_name="argument_sessions",
        help_text=_("The subject area for this argument"),
    )

    # Configuration
    difficulty = models.CharField(
        max_length=20,
        help_text=_("Difficulty level (beginner, intermediate, advanced)"),
    )
    heat_level = models.CharField(
        max_length=20,
        choices=HeatLevel.choices,
        default=HeatLevel.COLLEAGUE,
        help_text=_("How aggressive the AI opponent should be"),
    )

    # Content
    initial_prompt = models.TextField(
        help_text=_("The topic or scenario presented to start the argument"),
    )

    # State
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
        db_index=True,
        help_text=_("Current status of the argument session"),
    )
    message_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Total number of messages exchanged"),
    )

    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the argument was ended"),
    )

    class Meta:
        ordering = ["-started_at"]
        verbose_name = _("Argument Session")
        verbose_name_plural = _("Argument Sessions")
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["subject", "status"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.user.username} - {self.subject.name} "
            f"({self.get_heat_level_display()}) - {self.started_at:%Y-%m-%d}"
        )

    def get_absolute_url(self) -> str:
        """Get the URL for this session."""
        return reverse(
            "argument:session",
            kwargs={"subject_slug": self.subject.slug, "pk": self.pk},
        )

    def get_conversation_history(self) -> list[dict]:
        """
        Get conversation history for Claude API.

        Returns:
            list[dict]: List of message dicts in Claude API format.
        """
        messages = self.messages.order_by("created_at")
        history = []

        for msg in messages:
            # Map our roles to Claude API roles
            role = "user" if msg.role == ArgumentMessage.Role.USER else "assistant"
            history.append({
                "role": role,
                "content": msg.content,
            })

        return history

    def update_message_count(self) -> None:
        """Update message count from related messages."""
        self.message_count = self.messages.count()
        self.save(update_fields=["message_count"])


class ArgumentMessage(models.Model):
    """
    Individual message in an argument session.

    Messages alternate between user and opponent (AI) roles.
    """

    class Role(models.TextChoices):
        USER = "user", _("User")
        OPPONENT = "opponent", _("Opponent")

    # Relationships
    session = models.ForeignKey(
        ArgumentSession,
        on_delete=models.CASCADE,
        related_name="messages",
        help_text=_("The argument session this message belongs to"),
    )

    # Content
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        help_text=_("Who sent this message"),
    )
    content = models.TextField(
        help_text=_("Message content"),
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("Argument Message")
        verbose_name_plural = _("Argument Messages")
        indexes = [
            models.Index(fields=["session", "created_at"]),
        ]

    def __str__(self) -> str:
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"{self.get_role_display()}: {preview}"


class ArgumentAnalysis(models.Model):
    """
    End-of-session analysis of user's argument performance.

    When a user ends an argument, Claude analyzes the conversation
    and provides scores and feedback on three dimensions:
    technical correctness, temperament control, and topic focus.
    """

    # Relationships
    session = models.OneToOneField(
        ArgumentSession,
        on_delete=models.CASCADE,
        related_name="analysis",
        help_text=_("The argument session this analysis belongs to"),
    )

    # Scores (1-10 scale)
    technical_score = models.PositiveSmallIntegerField(
        help_text=_("Technical accuracy score (1-10)"),
    )
    temperament_score = models.PositiveSmallIntegerField(
        help_text=_("Emotional control score (1-10)"),
    )
    focus_score = models.PositiveSmallIntegerField(
        help_text=_("Topic focus score (1-10)"),
    )

    # Detailed feedback
    technical_feedback = models.TextField(
        help_text=_("Feedback on technical accuracy of user's arguments"),
    )
    temperament_feedback = models.TextField(
        help_text=_("Feedback on user's temperament and professionalism"),
    )
    focus_feedback = models.TextField(
        help_text=_("Feedback on staying on topic"),
    )
    overall_feedback = models.TextField(
        help_text=_("Overall summary and advice for improvement"),
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Argument Analysis")
        verbose_name_plural = _("Argument Analyses")

    def __str__(self) -> str:
        return (
            f"Analysis for {self.session.user.username} - "
            f"Tech: {self.technical_score}/10, "
            f"Temp: {self.temperament_score}/10, "
            f"Focus: {self.focus_score}/10"
        )

    @property
    def average_score(self) -> float:
        """Calculate average score across all dimensions."""
        return round(
            (self.technical_score + self.temperament_score + self.focus_score) / 3, 1
        )
