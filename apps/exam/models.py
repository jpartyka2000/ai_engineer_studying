"""Models for the exam app."""

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class ExamSession(models.Model):
    """
    Represents a single exam attempt by a user.

    Tracks the configuration, progress, and final score of an exam session.
    """

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", _("In Progress")
        COMPLETED = "completed", _("Completed")
        ABANDONED = "abandoned", _("Abandoned")

    # Relationships
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="exam_sessions",
        help_text=_("The user taking this exam"),
    )
    subject = models.ForeignKey(
        "subjects.Subject",
        on_delete=models.CASCADE,
        related_name="exam_sessions",
        help_text=_("The subject area for this exam"),
    )
    questions = models.ManyToManyField(
        "questions.Question",
        through="ExamAnswer",
        related_name="exam_sessions",
        help_text=_("Questions included in this exam"),
    )

    # Configuration
    difficulty = models.CharField(
        max_length=20,
        default="intermediate",
        help_text=_("Difficulty level selected for this exam"),
    )
    question_count = models.PositiveIntegerField(
        default=10,
        help_text=_("Number of questions in this exam"),
    )

    # Progress tracking
    current_question_index = models.PositiveIntegerField(
        default=0,
        help_text=_("Index of the current question (0-based)"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
        db_index=True,
        help_text=_("Current status of the exam session"),
    )

    # Scoring
    score = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of correct answers"),
    )
    total_answered = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of questions answered"),
    )

    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the exam was completed"),
    )

    class Meta:
        ordering = ["-started_at"]
        verbose_name = _("Exam Session")
        verbose_name_plural = _("Exam Sessions")

    def __str__(self) -> str:
        return (
            f"{self.user.username} - {self.subject.name} ({self.started_at:%Y-%m-%d})"
        )

    def get_absolute_url(self) -> str:
        """Return the URL for this exam session."""
        return reverse(
            "exam:session",
            kwargs={"subject_slug": self.subject.slug, "pk": self.pk},
        )

    @property
    def score_percentage(self) -> float:
        """Calculate the score as a percentage."""
        if self.total_answered == 0:
            return 0.0
        return round((self.score / self.total_answered) * 100, 1)

    @property
    def is_complete(self) -> bool:
        """Check if the exam has been completed."""
        return self.status == self.Status.COMPLETED

    @property
    def questions_remaining(self) -> int:
        """Calculate how many questions are left."""
        return self.question_count - self.current_question_index

    def get_current_question(self):
        """Get the current question to answer."""
        answers = self.answers.select_related("question").order_by("order")
        if self.current_question_index < len(answers):
            return answers[self.current_question_index].question
        return None

    def get_ordered_answers(self):
        """Get all answers in order."""
        return self.answers.select_related("question").order_by("order")


class ExamAnswer(models.Model):
    """
    Represents a user's answer to a question in an exam session.

    Links questions to sessions and stores the user's response.
    """

    # Relationships
    session = models.ForeignKey(
        ExamSession,
        on_delete=models.CASCADE,
        related_name="answers",
        help_text=_("The exam session this answer belongs to"),
    )
    question = models.ForeignKey(
        "questions.Question",
        on_delete=models.CASCADE,
        related_name="exam_answers",
        help_text=_("The question being answered"),
    )

    # Answer data
    user_answer = models.TextField(
        blank=True,
        help_text=_("The user's answer (option letter for MC, text for free)"),
    )
    is_correct = models.BooleanField(
        null=True,
        help_text=_("Whether the answer was correct (null if not yet answered)"),
    )
    is_flagged = models.BooleanField(
        default=False,
        help_text=_("Whether the user flagged this question for review"),
    )

    # Ordering
    order = models.PositiveIntegerField(
        default=0,
        help_text=_("Order of this question in the exam"),
    )

    # Timestamps
    answered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When this question was answered"),
    )

    class Meta:
        ordering = ["order"]
        verbose_name = _("Exam Answer")
        verbose_name_plural = _("Exam Answers")
        unique_together = [["session", "question"]]

    def __str__(self) -> str:
        status = (
            "Correct"
            if self.is_correct
            else "Incorrect"
            if self.is_correct is False
            else "Unanswered"
        )
        return f"Q{self.order + 1}: {status}"

    def check_answer(self) -> bool:
        """
        Check if the user's answer is correct and update is_correct.

        For multiple choice: compares option letter (case-insensitive)
        For free text: uses fuzzy matching (TODO: implement with Claude)
        """
        if not self.user_answer:
            self.is_correct = False
            return False

        if self.question.is_multiple_choice:
            # For MC, compare the letter (case-insensitive)
            self.is_correct = (
                self.user_answer.strip().upper()
                == self.question.correct_answer.strip().upper()
            )
        else:
            # For free text, we'll need Claude to evaluate
            # For now, do exact match (case-insensitive)
            self.is_correct = (
                self.user_answer.strip().lower()
                == self.question.correct_answer.strip().lower()
            )

        return self.is_correct
