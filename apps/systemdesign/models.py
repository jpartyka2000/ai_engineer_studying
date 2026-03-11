"""Models for the System Design study mode."""

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class SystemDesignChallenge(models.Model):
    """
    Represents a system design challenge template.

    Can be pre-defined by admins or generated on-demand by LLM ("surprise" challenges).
    """

    class Difficulty(models.TextChoices):
        BEGINNER = "beginner", _("Beginner")  # 15 min
        INTERMEDIATE = "intermediate", _("Intermediate")  # 30 min
        ADVANCED = "advanced", _("Advanced")  # 45 min

    class Source(models.TextChoices):
        MANUAL = "manual", _("Manually Created")
        LLM_GENERATED = "llm", _("LLM Generated")

    TIME_LIMITS = {
        "beginner": 900,  # 15 minutes
        "intermediate": 1800,  # 30 minutes
        "advanced": 2700,  # 45 minutes
    }

    # Core fields
    title = models.CharField(
        max_length=200,
        help_text=_("Challenge title, e.g., 'Design Twitter'"),
    )
    slug = models.SlugField(
        unique=True,
        help_text=_("URL-safe identifier"),
    )
    description = models.TextField(
        help_text=_("Full problem statement presented to the user"),
    )

    # Requirements and constraints
    functional_requirements = models.JSONField(
        default=list,
        help_text=_("List of functional requirements the design should address"),
    )
    non_functional_requirements = models.JSONField(
        default=list,
        help_text=_("List of non-functional requirements (scalability, latency, etc.)"),
    )
    constraints = models.JSONField(
        default=list,
        help_text=_("System constraints (budget, region, compliance)"),
    )

    # Evaluation criteria
    evaluation_criteria = models.JSONField(
        default=dict,
        help_text=_("Rubric criteria with weights: {scalability: 10, reliability: 10, ...}"),
    )

    # Reference solution (for LLM comparison)
    reference_solution_description = models.TextField(
        blank=True,
        help_text=_("Text description of an ideal solution approach"),
    )
    reference_components = models.JSONField(
        default=list,
        help_text=_("Expected components: ['load_balancer', 'cache', 'database', ...]"),
    )

    # Metadata
    difficulty = models.CharField(
        max_length=20,
        choices=Difficulty.choices,
        default=Difficulty.INTERMEDIATE,
        db_index=True,
    )
    time_limit_seconds = models.PositiveIntegerField(
        default=1800,  # 30 minutes
        help_text=_("Time limit based on difficulty"),
    )
    source = models.CharField(
        max_length=10,
        choices=Source.choices,
        default=Source.MANUAL,
    )
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Tags for categorization"),
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        db_index=True,
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["difficulty", "title"]
        verbose_name = _("System Design Challenge")
        verbose_name_plural = _("System Design Challenges")

    def __str__(self) -> str:
        return f"{self.title} ({self.get_difficulty_display()})"

    def save(self, *args, **kwargs) -> None:
        """Set time limit based on difficulty if not explicitly set."""
        if not self.time_limit_seconds or self.time_limit_seconds == 1800:
            self.time_limit_seconds = self.TIME_LIMITS.get(self.difficulty, 1800)
        super().save(*args, **kwargs)


class SystemDesignSession(models.Model):
    """
    Represents a single system design attempt by a user.

    Combines timer, canvas state, chat history, and analysis snapshots.
    """

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", _("In Progress")
        SUBMITTED = "submitted", _("Submitted for Scoring")
        COMPLETED = "completed", _("Completed")
        TIMED_OUT = "timed_out", _("Timed Out")
        ABANDONED = "abandoned", _("Abandoned")

    TIME_LIMIT_CHOICES = [
        (900, _("15 minutes")),  # Beginner
        (1800, _("30 minutes")),  # Intermediate
        (2700, _("45 minutes")),  # Advanced
    ]

    # Relationships
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="systemdesign_sessions",
    )
    challenge = models.ForeignKey(
        SystemDesignChallenge,
        on_delete=models.CASCADE,
        related_name="sessions",
        null=True,  # null for "surprise" challenges
        blank=True,
    )

    # Surprise challenge data (when challenge is null)
    surprise_challenge_data = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("LLM-generated challenge details when using surprise mode"),
    )

    # Configuration (snapshot at session start)
    difficulty = models.CharField(
        max_length=20,
        choices=SystemDesignChallenge.Difficulty.choices,
        default=SystemDesignChallenge.Difficulty.INTERMEDIATE,
    )
    time_limit_seconds = models.PositiveIntegerField(default=1800)

    # Canvas state
    canvas_state = models.JSONField(
        default=dict,
        help_text=_("Fabric.js canvas JSON state for persistence"),
    )
    canvas_snapshot_png = models.BinaryField(
        null=True,
        blank=True,
        help_text=_("Latest PNG snapshot of the canvas for vision analysis"),
    )

    # Progress tracking
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
        db_index=True,
    )

    # Timer tracking
    started_at = models.DateTimeField(auto_now_add=True)
    last_analysis_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the last auto-analysis was performed"),
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = _("System Design Session")
        verbose_name_plural = _("System Design Sessions")
        indexes = [
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.user.username} - {self.effective_challenge_title}"

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
        """Check if the timer has expired."""
        return self.time_remaining_seconds <= 0

    @property
    def time_elapsed_seconds(self) -> int:
        """Calculate elapsed time in seconds."""
        elapsed = (timezone.now() - self.started_at).total_seconds()
        return min(int(elapsed), self.time_limit_seconds)

    @property
    def progress_percentage(self) -> float:
        """Calculate time progress as a percentage."""
        if self.time_limit_seconds == 0:
            return 100.0
        return min(100.0, (self.time_elapsed_seconds / self.time_limit_seconds) * 100)

    @property
    def effective_challenge_title(self) -> str:
        """Return challenge title whether pre-defined or surprise."""
        if self.challenge:
            return self.challenge.title
        return self.surprise_challenge_data.get("title", "Surprise Challenge")

    @property
    def effective_description(self) -> str:
        """Return challenge description whether pre-defined or surprise."""
        if self.challenge:
            return self.challenge.description
        return self.surprise_challenge_data.get("description", "")

    @property
    def effective_functional_requirements(self) -> list:
        """Return functional requirements whether pre-defined or surprise."""
        if self.challenge:
            return self.challenge.functional_requirements
        return self.surprise_challenge_data.get("functional_requirements", [])

    @property
    def effective_non_functional_requirements(self) -> list:
        """Return non-functional requirements whether pre-defined or surprise."""
        if self.challenge:
            return self.challenge.non_functional_requirements
        return self.surprise_challenge_data.get("non_functional_requirements", [])

    @property
    def effective_constraints(self) -> list:
        """Return constraints whether pre-defined or surprise."""
        if self.challenge:
            return self.challenge.constraints
        return self.surprise_challenge_data.get("constraints", [])

    def get_conversation_history(self, max_tokens: int = 50000) -> list[dict]:
        """
        Get conversation history for LLM API, truncated to fit token limit.

        Args:
            max_tokens: Maximum tokens to include in history.

        Returns:
            List of message dicts with 'role' and 'content' keys.
        """
        messages = self.messages.order_by("created_at")
        history = []
        token_count = 0

        # Build from most recent, then reverse
        for msg in reversed(list(messages)):
            if token_count + msg.token_count_estimate > max_tokens:
                break
            history.insert(0, {"role": msg.role, "content": msg.content})
            token_count += msg.token_count_estimate

        return history

    def end_session(self, status: str) -> None:
        """
        End the session with the given status.

        Args:
            status: The final status (completed, timed_out, abandoned).
        """
        self.status = status
        if status == self.Status.SUBMITTED:
            self.submitted_at = timezone.now()
        elif status in (self.Status.COMPLETED, self.Status.TIMED_OUT, self.Status.ABANDONED):
            self.completed_at = timezone.now()
        self.save(update_fields=["status", "submitted_at", "completed_at"])


class SystemDesignMessage(models.Model):
    """
    Represents a chat message in the system design session.

    Used for requirements clarification and hint requests.
    """

    class Role(models.TextChoices):
        USER = "user", _("User")
        ASSISTANT = "assistant", _("Interviewer")
        SYSTEM = "system", _("System")  # For auto-generated messages

    class MessageType(models.TextChoices):
        CLARIFICATION = "clarification", _("Clarification Question")
        HINT = "hint", _("Hint Request")
        ANALYSIS = "analysis", _("Diagram Analysis")
        GENERAL = "general", _("General Discussion")
        INITIAL = "initial", _("Initial Prompt")

    session = models.ForeignKey(
        SystemDesignSession,
        on_delete=models.CASCADE,
        related_name="messages",
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
    )
    content = models.TextField()
    message_type = models.CharField(
        max_length=20,
        choices=MessageType.choices,
        default=MessageType.GENERAL,
    )

    # Token tracking for context management
    token_count_estimate = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["session", "created_at"]),
        ]

    def __str__(self) -> str:
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"{self.get_role_display()}: {preview}"

    def save(self, *args, **kwargs) -> None:
        """Estimate token count on save."""
        if not self.token_count_estimate:
            self.token_count_estimate = len(self.content) // 4
        super().save(*args, **kwargs)


class DiagramAnalysis(models.Model):
    """
    Stores a snapshot analysis of the user's diagram.

    Created periodically (every 5 min) and on-demand via button click.
    """

    class AnalysisType(models.TextChoices):
        PERIODIC = "periodic", _("Periodic Auto-Analysis")
        ON_DEMAND = "on_demand", _("On-Demand Analysis")
        FINAL = "final", _("Final Submission Analysis")

    session = models.ForeignKey(
        SystemDesignSession,
        on_delete=models.CASCADE,
        related_name="analyses",
    )

    analysis_type = models.CharField(
        max_length=20,
        choices=AnalysisType.choices,
        default=AnalysisType.PERIODIC,
    )

    # Snapshot at time of analysis
    canvas_state_snapshot = models.JSONField(
        default=dict,
        help_text=_("Fabric.js JSON state at time of analysis"),
    )
    canvas_png_snapshot = models.BinaryField(
        null=True,
        blank=True,
        help_text=_("PNG snapshot at time of analysis"),
    )

    # Analysis results
    identified_components = models.JSONField(
        default=list,
        help_text=_("Components detected in the diagram"),
    )
    identified_connections = models.JSONField(
        default=list,
        help_text=_("Data flows/connections detected"),
    )

    # Preliminary feedback
    strengths = models.JSONField(default=list)
    concerns = models.JSONField(default=list)
    suggestions = models.JSONField(default=list)
    overall_impression = models.TextField(blank=True)

    # Scores (preliminary, not final)
    preliminary_scores = models.JSONField(
        default=dict,
        help_text=_("Preliminary scores: {scalability: 6, reliability: 7, ...}"),
    )

    # Raw LLM response for debugging
    raw_response = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Raw response from the vision API"),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Diagram Analysis")
        verbose_name_plural = _("Diagram Analyses")

    def __str__(self) -> str:
        return f"Analysis for {self.session} at {self.created_at}"


class SystemDesignScore(models.Model):
    """
    Final scores and detailed feedback for a completed session.

    Created when the user submits their design.
    """

    session = models.OneToOneField(
        SystemDesignSession,
        on_delete=models.CASCADE,
        related_name="final_score",
    )

    # Individual rubric scores (1-10 each)
    scalability_score = models.PositiveIntegerField(
        default=0,
        help_text=_("Score for scalability considerations (1-10)"),
    )
    reliability_score = models.PositiveIntegerField(
        default=0,
        help_text=_("Score for fault tolerance and reliability (1-10)"),
    )
    performance_score = models.PositiveIntegerField(
        default=0,
        help_text=_("Score for performance optimization (1-10)"),
    )
    cost_efficiency_score = models.PositiveIntegerField(
        default=0,
        help_text=_("Score for cost-effective choices (1-10)"),
    )
    communication_score = models.PositiveIntegerField(
        default=0,
        help_text=_("Score for communication quality in chat (1-10)"),
    )

    # Overall (weighted average, 1-100)
    overall_score = models.PositiveIntegerField(
        default=0,
        help_text=_("Weighted overall score (1-100)"),
    )

    # Narrative feedback
    strengths_narrative = models.TextField(
        blank=True,
        help_text=_("What the user did well"),
    )
    weaknesses_narrative = models.TextField(
        blank=True,
        help_text=_("Areas for improvement"),
    )
    design_coherence_feedback = models.TextField(
        blank=True,
        help_text=_("How well the components work together"),
    )
    comparison_to_reference = models.TextField(
        blank=True,
        help_text=_("Comparison to the reference/ideal solution"),
    )

    # Detailed breakdown
    detailed_feedback = models.JSONField(
        default=dict,
        help_text=_("Full scoring breakdown with justifications per category"),
    )

    # LLM response metadata
    scoring_model_used = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Model used for scoring (e.g., claude-3-opus)"),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("System Design Score")
        verbose_name_plural = _("System Design Scores")

    def __str__(self) -> str:
        return f"Score for {self.session}: {self.overall_score}/100"

    def calculate_overall_score(self) -> int:
        """
        Calculate the weighted overall score.

        All categories are weighted equally at 20% each.
        """
        scores = [
            self.scalability_score,
            self.reliability_score,
            self.performance_score,
            self.cost_efficiency_score,
            self.communication_score,
        ]
        # Each score is 1-10, weight is 20% each, so multiply by 2 for 100-point scale
        return sum(scores) * 2

    def save(self, *args, **kwargs) -> None:
        """Calculate overall score before saving."""
        self.overall_score = self.calculate_overall_score()
        super().save(*args, **kwargs)
