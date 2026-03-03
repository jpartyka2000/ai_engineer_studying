"""Models for the lightning round app."""

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class LightningSession(models.Model):
    """
    Represents a lightning round session.

    Lightning rounds are timed challenges where users answer as many
    multiple choice questions as possible before time runs out.
    """

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", _("In Progress")
        COMPLETED = "completed", _("Completed")
        TIMED_OUT = "timed_out", _("Timed Out")

    TIME_LIMIT_CHOICES = [
        (60, _("1 minute")),
        (120, _("2 minutes")),
        (180, _("3 minutes")),
        (300, _("5 minutes")),
        (600, _("10 minutes")),
        (900, _("15 minutes")),
    ]

    # Relationships
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="lightning_sessions",
        help_text=_("The user taking this lightning round"),
    )
    subject = models.ForeignKey(
        "subjects.Subject",
        on_delete=models.CASCADE,
        related_name="lightning_sessions",
        help_text=_("The subject area for this lightning round"),
    )

    # Configuration
    difficulty = models.CharField(
        max_length=20,
        default="intermediate",
        help_text=_("Difficulty level for questions"),
    )
    time_limit_seconds = models.PositiveIntegerField(
        default=300,
        choices=TIME_LIMIT_CHOICES,
        help_text=_("Time limit in seconds"),
    )

    # Progress tracking
    questions_answered = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of questions answered"),
    )
    questions_correct = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of correct answers"),
    )
    current_streak = models.PositiveIntegerField(
        default=0,
        help_text=_("Current consecutive correct answers"),
    )
    best_streak = models.PositiveIntegerField(
        default=0,
        help_text=_("Best streak achieved in this session"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
        db_index=True,
        help_text=_("Current status of the session"),
    )

    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the session ended"),
    )

    class Meta:
        ordering = ["-started_at"]
        verbose_name = _("Lightning Session")
        verbose_name_plural = _("Lightning Sessions")

    def __str__(self) -> str:
        return f"{self.user.username} - {self.subject.name} Lightning ({self.started_at:%Y-%m-%d})"

    def get_absolute_url(self) -> str:
        """Return the URL for this lightning session."""
        return reverse(
            "lightning:play",
            kwargs={"subject_slug": self.subject.slug, "pk": self.pk},
        )

    def get_results_url(self) -> str:
        """Return the URL for the results page."""
        return reverse(
            "lightning:results",
            kwargs={"subject_slug": self.subject.slug, "pk": self.pk},
        )

    @property
    def time_remaining_seconds(self) -> int:
        """Calculate remaining time in seconds."""
        if self.status != self.Status.IN_PROGRESS:
            return 0
        elapsed = (timezone.now() - self.started_at).total_seconds()
        remaining = self.time_limit_seconds - elapsed
        return max(0, int(remaining))

    @property
    def is_time_up(self) -> bool:
        """Check if time has expired."""
        return self.time_remaining_seconds <= 0

    @property
    def accuracy_percentage(self) -> float:
        """Calculate accuracy as a percentage."""
        if self.questions_answered == 0:
            return 0.0
        return round((self.questions_correct / self.questions_answered) * 100, 1)

    @property
    def average_time_per_question(self) -> float:
        """Calculate average seconds per question answered."""
        if self.questions_answered == 0:
            return 0.0
        elapsed = (timezone.now() - self.started_at).total_seconds()
        if self.completed_at:
            elapsed = (self.completed_at - self.started_at).total_seconds()
        return round(elapsed / self.questions_answered, 1)

    def record_answer(self, is_correct: bool) -> None:
        """Record an answer and update stats."""
        self.questions_answered += 1
        if is_correct:
            self.questions_correct += 1
            self.current_streak += 1
            if self.current_streak > self.best_streak:
                self.best_streak = self.current_streak
        else:
            self.current_streak = 0

    def end_session(self, timed_out: bool = False) -> None:
        """End the lightning session."""
        self.status = self.Status.TIMED_OUT if timed_out else self.Status.COMPLETED
        self.completed_at = timezone.now()


class LightningAnswer(models.Model):
    """
    Tracks individual answers in a lightning session for review.

    Lighter weight than ExamAnswer since lightning rounds don't need
    flagging or detailed review during the session.
    """

    session = models.ForeignKey(
        LightningSession,
        on_delete=models.CASCADE,
        related_name="answers",
        help_text=_("The lightning session this answer belongs to"),
    )
    question = models.ForeignKey(
        "questions.Question",
        on_delete=models.CASCADE,
        related_name="lightning_answers",
        help_text=_("The question that was answered"),
    )
    user_answer = models.CharField(
        max_length=10,
        help_text=_("The user's answer (option letter)"),
    )
    is_correct = models.BooleanField(
        help_text=_("Whether the answer was correct"),
    )
    answered_at = models.DateTimeField(auto_now_add=True)
    response_time_ms = models.PositiveIntegerField(
        default=0,
        help_text=_("Time taken to answer in milliseconds"),
    )

    class Meta:
        ordering = ["answered_at"]
        verbose_name = _("Lightning Answer")
        verbose_name_plural = _("Lightning Answers")

    def __str__(self) -> str:
        status = "Correct" if self.is_correct else "Incorrect"
        return f"{status} - {self.question.question_text[:30]}..."
