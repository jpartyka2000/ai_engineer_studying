"""Models for user progress tracking and study streaks."""

from datetime import date, timedelta

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserProgress(models.Model):
    """
    Tracks aggregated user progress per subject.

    Stores cumulative statistics from exam, lightning, and Q&A sessions
    for efficient dashboard rendering without expensive aggregation queries.
    """

    # Relationships
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="progress_records",
        help_text=_("The user this progress belongs to"),
    )
    subject = models.ForeignKey(
        "subjects.Subject",
        on_delete=models.CASCADE,
        related_name="user_progress",
        help_text=_("The subject area for this progress"),
    )

    # Exam statistics
    exam_sessions = models.PositiveIntegerField(
        default=0,
        help_text=_("Total completed exam sessions"),
    )
    exam_correct = models.PositiveIntegerField(
        default=0,
        help_text=_("Total correct answers in exams"),
    )
    exam_total = models.PositiveIntegerField(
        default=0,
        help_text=_("Total questions answered in exams"),
    )

    # Lightning round statistics
    lightning_sessions = models.PositiveIntegerField(
        default=0,
        help_text=_("Total completed lightning sessions"),
    )
    lightning_correct = models.PositiveIntegerField(
        default=0,
        help_text=_("Total correct answers in lightning rounds"),
    )
    lightning_total = models.PositiveIntegerField(
        default=0,
        help_text=_("Total questions answered in lightning rounds"),
    )
    lightning_best_streak = models.PositiveIntegerField(
        default=0,
        help_text=_("Best streak achieved in lightning rounds"),
    )

    # Q&A statistics
    qa_sessions = models.PositiveIntegerField(
        default=0,
        help_text=_("Total Q&A sessions started"),
    )

    # Argument statistics
    argument_sessions = models.PositiveIntegerField(
        default=0,
        help_text=_("Total completed argument sessions"),
    )
    argument_avg_technical = models.FloatField(
        default=0.0,
        help_text=_("Average technical accuracy score (1-10)"),
    )
    argument_avg_temperament = models.FloatField(
        default=0.0,
        help_text=_("Average temperament control score (1-10)"),
    )
    argument_avg_focus = models.FloatField(
        default=0.0,
        help_text=_("Average topic focus score (1-10)"),
    )

    # Timestamps
    last_studied_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When this subject was last studied"),
    )

    class Meta:
        ordering = ["-last_studied_at"]
        verbose_name = _("User Progress")
        verbose_name_plural = _("User Progress Records")
        unique_together = [["user", "subject"]]
        indexes = [
            models.Index(fields=["user", "-last_studied_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user.username} - {self.subject.name}"

    @property
    def total_sessions(self) -> int:
        """Total sessions across all modes."""
        return (
            self.exam_sessions
            + self.lightning_sessions
            + self.qa_sessions
            + self.argument_sessions
        )

    @property
    def total_correct(self) -> int:
        """Total correct answers across exam and lightning modes."""
        return self.exam_correct + self.lightning_correct

    @property
    def total_questions(self) -> int:
        """Total questions answered across exam and lightning modes."""
        return self.exam_total + self.lightning_total

    @property
    def accuracy_percentage(self) -> float:
        """Calculate overall accuracy as a percentage."""
        if self.total_questions == 0:
            return 0.0
        return round((self.total_correct / self.total_questions) * 100, 1)

    @property
    def exam_accuracy(self) -> float:
        """Calculate exam-specific accuracy."""
        if self.exam_total == 0:
            return 0.0
        return round((self.exam_correct / self.exam_total) * 100, 1)

    @property
    def lightning_accuracy(self) -> float:
        """Calculate lightning-specific accuracy."""
        if self.lightning_total == 0:
            return 0.0
        return round((self.lightning_correct / self.lightning_total) * 100, 1)


class StudyStreak(models.Model):
    """
    Tracks daily study activity and streak for a user.

    A streak is maintained by completing at least one session (any mode)
    each day. Missing a day resets the current streak.
    """

    # Relationship
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="study_streak",
        help_text=_("The user this streak belongs to"),
    )

    # Streak data
    current_streak = models.PositiveIntegerField(
        default=0,
        help_text=_("Current consecutive days of study"),
    )
    longest_streak = models.PositiveIntegerField(
        default=0,
        help_text=_("Longest streak ever achieved"),
    )
    last_activity_date = models.DateField(
        null=True,
        blank=True,
        help_text=_("Date of most recent study activity"),
    )

    class Meta:
        verbose_name = _("Study Streak")
        verbose_name_plural = _("Study Streaks")

    def __str__(self) -> str:
        return f"{self.user.username}: {self.current_streak} day streak"

    def record_activity(self, activity_date: date | None = None) -> None:
        """
        Update streak based on activity date.

        Args:
            activity_date: The date of activity. Defaults to today.
        """
        if activity_date is None:
            activity_date = date.today()

        if self.last_activity_date is None:
            # First ever activity
            self.current_streak = 1
        elif activity_date == self.last_activity_date:
            # Already recorded activity today, no change needed
            return
        elif activity_date == self.last_activity_date + timedelta(days=1):
            # Consecutive day - extend streak
            self.current_streak += 1
        elif activity_date > self.last_activity_date + timedelta(days=1):
            # Missed one or more days - reset streak
            self.current_streak = 1
        # Note: activity_date < last_activity_date is ignored (past date)

        # Update longest streak if needed
        if self.current_streak > self.longest_streak:
            self.longest_streak = self.current_streak

        self.last_activity_date = activity_date
        self.save()

    @property
    def is_active_today(self) -> bool:
        """Check if user has studied today."""
        return self.last_activity_date == date.today()

    @property
    def streak_status(self) -> str:
        """Get human-readable streak status."""
        if self.last_activity_date is None:
            return "No activity yet"
        if self.is_active_today:
            return f"{self.current_streak} day streak - Keep it up!"
        if self.last_activity_date == date.today() - timedelta(days=1):
            return f"{self.current_streak} day streak - Study today to continue!"
        return "Streak ended - Start a new one!"
