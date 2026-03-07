"""Models for the equations (Can I Math?) app."""

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class MathProblem(models.Model):
    """
    A mathematical equation problem for practice.

    Supports multiple problem types:
    - Complete: Fill in the blank in an equation
    - Solve: Write the full equation/solution from scratch
    - Multiple Choice: Select the correct equation from options
    """

    class ProblemType(models.TextChoices):
        COMPLETE = "complete", _("Complete the Equation")
        SOLVE = "solve", _("Solve from Scratch")
        MULTIPLE_CHOICE = "mc", _("Multiple Choice")

    class Difficulty(models.TextChoices):
        BEGINNER = "beginner", _("Beginner")
        INTERMEDIATE = "intermediate", _("Intermediate")
        ADVANCED = "advanced", _("Advanced")

    class Source(models.TextChoices):
        MANUAL = "manual", _("Manually Created")
        CLAUDE_API = "claude_api", _("Claude API Generated")

    # Relationship
    subject = models.ForeignKey(
        "subjects.Subject",
        on_delete=models.CASCADE,
        related_name="math_problems",
        help_text=_("The subject area this problem belongs to"),
    )

    # Problem type and difficulty
    problem_type = models.CharField(
        max_length=20,
        choices=ProblemType.choices,
        default=ProblemType.COMPLETE,
        db_index=True,
        help_text=_("Type of problem"),
    )
    difficulty = models.CharField(
        max_length=20,
        choices=Difficulty.choices,
        default=Difficulty.INTERMEDIATE,
        db_index=True,
        help_text=_("Difficulty level"),
    )

    # Problem content
    problem_text = models.TextField(
        help_text=_("Plain text description of the problem"),
    )
    problem_latex = models.TextField(
        help_text=_("The equation/problem in LaTeX format"),
    )
    blank_placeholder = models.CharField(
        max_length=50,
        default="_____",
        blank=True,
        help_text=_("Placeholder text for the blank (for complete type)"),
    )

    # Answer(s)
    correct_answer_latex = models.TextField(
        help_text=_("The correct answer in LaTeX format"),
    )
    acceptable_alternatives = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Alternative correct forms in LaTeX"),
    )

    # For multiple choice problems
    options = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Answer options as LaTeX strings (for MC type)"),
    )
    correct_option = models.CharField(
        max_length=1,
        blank=True,
        help_text=_("The correct option letter (A, B, C, D) for MC type"),
    )

    # Metadata
    topic = models.CharField(
        max_length=100,
        help_text=_("Specific topic (e.g., 'Bellman Equation', 'Policy Gradient')"),
    )
    explanation = models.TextField(
        blank=True,
        help_text=_("Explanation of the correct answer"),
    )
    hints = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Progressive hints for the problem"),
    )
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Tags for categorization"),
    )

    # Source tracking
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.MANUAL,
        db_index=True,
        help_text=_("How this problem was created"),
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text=_("Whether this problem is available for use"),
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Math Problem")
        verbose_name_plural = _("Math Problems")
        indexes = [
            models.Index(fields=["subject", "difficulty", "is_active"]),
            models.Index(fields=["subject", "problem_type", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.topic}: {self.problem_text[:50]}..."


class MathSession(models.Model):
    """
    A user's math practice session.

    Tracks configuration, progress, and completion status.
    """

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", _("In Progress")
        COMPLETED = "completed", _("Completed")
        ABANDONED = "abandoned", _("Abandoned")

    # Relationships
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="math_sessions",
        help_text=_("The user taking this session"),
    )
    subject = models.ForeignKey(
        "subjects.Subject",
        on_delete=models.CASCADE,
        related_name="math_sessions",
        help_text=_("The subject area for this session"),
    )

    # Configuration
    difficulty = models.CharField(
        max_length=20,
        choices=MathProblem.Difficulty.choices,
        help_text=_("Difficulty level for this session"),
    )
    problem_types = models.JSONField(
        default=list,
        help_text=_("Selected problem types for this session"),
    )
    topic_filter = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Optional topic filter"),
    )
    llm_provider = models.CharField(
        max_length=20,
        default="openai",
        help_text=_("LLM provider for AI evaluation (claude or openai)"),
    )

    # Progress tracking
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
        db_index=True,
        help_text=_("Current status of the session"),
    )
    current_problem_index = models.PositiveIntegerField(
        default=0,
        help_text=_("Index of current problem (0-based)"),
    )
    total_problems = models.PositiveIntegerField(
        default=10,
        help_text=_("Total number of problems in this session"),
    )

    # Scoring
    score = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of problems answered correctly"),
    )
    total_points = models.FloatField(
        default=0.0,
        help_text=_("Total points including partial credit"),
    )

    # Problems for this session (ordered)
    problems = models.ManyToManyField(
        MathProblem,
        through="MathSessionProblem",
        related_name="sessions",
    )

    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the session was completed"),
    )

    class Meta:
        ordering = ["-started_at"]
        verbose_name = _("Math Session")
        verbose_name_plural = _("Math Sessions")
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["subject", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.user.username} - {self.subject.name} ({self.started_at:%Y-%m-%d})"

    def get_absolute_url(self) -> str:
        """Return the URL for this session."""
        return reverse(
            "equations:problem",
            kwargs={"subject_slug": self.subject.slug, "pk": self.pk},
        )

    @property
    def is_complete(self) -> bool:
        """Check if the session is completed."""
        return self.status == self.Status.COMPLETED

    @property
    def progress_percentage(self) -> int:
        """Calculate progress as a percentage."""
        if self.total_problems == 0:
            return 0
        answered = self.answers.count()
        return int((answered / self.total_problems) * 100)

    @property
    def accuracy_percentage(self) -> float:
        """Calculate accuracy as a percentage."""
        answered = self.answers.count()
        if answered == 0:
            return 0.0
        return (self.total_points / answered) * 100

    def get_current_problem(self) -> MathProblem | None:
        """Get the current problem for this session."""
        try:
            session_problem = self.session_problems.get(order=self.current_problem_index)
            return session_problem.problem
        except MathSessionProblem.DoesNotExist:
            return None


class MathSessionProblem(models.Model):
    """
    Through model linking MathSession to MathProblem with ordering.

    This allows us to maintain a specific order of problems for each session.
    """

    session = models.ForeignKey(
        MathSession,
        on_delete=models.CASCADE,
        related_name="session_problems",
    )
    problem = models.ForeignKey(
        MathProblem,
        on_delete=models.CASCADE,
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text=_("Order of this problem in the session"),
    )

    class Meta:
        ordering = ["order"]
        unique_together = [["session", "order"]]
        verbose_name = _("Session Problem")
        verbose_name_plural = _("Session Problems")

    def __str__(self) -> str:
        return f"Session {self.session.pk} - Problem {self.order + 1}"


class MathAnswer(models.Model):
    """
    A user's answer to a math problem within a session.

    Stores the user's LaTeX input and Claude's evaluation.
    """

    # Relationships
    session = models.ForeignKey(
        MathSession,
        on_delete=models.CASCADE,
        related_name="answers",
        help_text=_("The session this answer belongs to"),
    )
    problem = models.ForeignKey(
        MathProblem,
        on_delete=models.CASCADE,
        related_name="answers",
        help_text=_("The problem being answered"),
    )

    # User's answer
    user_answer_latex = models.TextField(
        help_text=_("The user's answer in LaTeX format"),
    )
    selected_option = models.CharField(
        max_length=1,
        blank=True,
        help_text=_("Selected option for MC problems (A, B, C, D)"),
    )

    # Evaluation results
    is_correct = models.BooleanField(
        null=True,
        help_text=_("Whether the answer is fully correct"),
    )
    partial_credit = models.FloatField(
        null=True,
        blank=True,
        help_text=_("Partial credit score (0.0 to 1.0)"),
    )

    # Claude feedback
    feedback = models.TextField(
        blank=True,
        help_text=_("Feedback from Claude on the answer"),
    )
    mathematical_errors = models.JSONField(
        default=list,
        blank=True,
        help_text=_("List of specific mathematical errors identified"),
    )

    # Metadata
    hints_used = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of hints the user revealed"),
    )
    time_taken_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Time taken to answer in seconds"),
    )

    # Timestamps
    answered_at = models.DateTimeField(auto_now_add=True)
    evaluated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the answer was evaluated"),
    )

    class Meta:
        ordering = ["answered_at"]
        verbose_name = _("Math Answer")
        verbose_name_plural = _("Math Answers")
        indexes = [
            models.Index(fields=["session", "problem"]),
        ]

    def __str__(self) -> str:
        status = "Correct" if self.is_correct else "Incorrect" if self.is_correct is False else "Pending"
        return f"{self.problem.topic}: {status}"

    @property
    def score(self) -> float:
        """Calculate the score for this answer (0.0 to 1.0)."""
        if self.is_correct:
            return 1.0
        if self.partial_credit is not None:
            return self.partial_credit
        return 0.0
