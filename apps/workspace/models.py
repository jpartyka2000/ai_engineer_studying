"""Models for workspace mode ("Work With Existing Codebase").

Six models: an authored :class:`WorkspaceExercise`, a per-attempt
:class:`WorkspaceSession`, the captured :class:`WorkspaceSubmission`, the
per-check :class:`WorkspaceCheckResult`, the resulting :class:`WorkspaceGrade`,
and a :class:`WorkspaceEvent` audit trail.

Two deliberate departures from the rest of the project are worth knowing about:

* **The deadline is stored absolutely.** ``apps/lightning`` derives remaining time
  from ``started_at``, which works there only because its ``started_at`` is
  ``auto_now_add`` -- the clock starts the instant the row is created. Here,
  scaffolding and container bring-up happen *before* the clock starts, so
  ``started_at`` is set explicitly and ``expires_at`` is the authority.
* **Nothing here feeds readiness scoring.** ``apps/readiness`` weights its four
  modes to sum to 1.0, and one exercise spans FastAPI, Docker, Postgres and pytest
  at once, so it cannot be attributed to a single subject. This mode reports its
  own history instead.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.workspace.enums import (
    BaseApp,
    CheckKind,
    CheckStatus,
    Difficulty,
    ExerciseType,
    LetterGrade,
    ObjectiveStatus,
)

#: Selectable time limits, in seconds. Mirrors the idiom in
#: ``apps/lightning/models.py`` and is bounded by the 20-60 minute requirement.
TIME_LIMIT_CHOICES = [
    (20 * 60, _("20 minutes")),
    (25 * 60, _("25 minutes")),
    (30 * 60, _("30 minutes")),
    (35 * 60, _("35 minutes")),
    (40 * 60, _("40 minutes")),
    (45 * 60, _("45 minutes")),
    (50 * 60, _("50 minutes")),
    (55 * 60, _("55 minutes")),
    (60 * 60, _("60 minutes")),
]


class WorkspaceExercise(models.Model):
    """One authored exercise: a base application plus an injected defect or ask.

    Exercises are ``(base_app, mutations)`` pairs rather than standalone
    codebases, which is what makes a catalog of 50 authorable.
    """

    exercise_number = models.PositiveSmallIntegerField(
        unique=True,
        db_index=True,
        help_text=_("Stable 1-50 number, used in the on-disk directory name"),
    )
    slug = models.SlugField(
        max_length=120,
        unique=True,
        help_text=_("URL and directory identifier, e.g. 'ex-017-tenant-isolation'"),
    )
    title = models.CharField(
        max_length=200, help_text=_("Shown in the catalog, phrased as a ticket title")
    )
    exercise_type = models.CharField(
        max_length=30,
        choices=ExerciseType.choices,
        db_index=True,
        help_text=_("Which of the ten kinds of work this exercise asks for"),
    )
    base_app = models.CharField(
        max_length=30,
        choices=BaseApp.choices,
        db_index=True,
        help_text=_("Which base application template this exercise is built on"),
    )
    difficulty = models.CharField(
        max_length=20,
        choices=Difficulty.choices,
        db_index=True,
        help_text=_("Driven by how many files must change and how hard they are to find"),
    )
    defect_class = models.CharField(
        max_length=60,
        db_index=True,
        help_text=_(
            "Closed-vocabulary defect category, e.g. 'n_plus_one'. Used to enforce "
            "variety: no class may appear more than twice across the catalog"
        ),
    )

    brief_md = models.TextField(help_text=_("Markdown ticket the user reads before starting"))
    definition_of_done = models.JSONField(
        default=list,
        help_text=_("User-facing checklist; each item maps to a check id or 'llm'"),
    )

    time_limit_seconds = models.PositiveIntegerField(
        choices=TIME_LIMIT_CHOICES,
        validators=[
            MinValueValidator(settings.WORKSPACE_MIN_TIME_LIMIT_SECONDS),
            MaxValueValidator(settings.WORKSPACE_MAX_TIME_LIMIT_SECONDS),
        ],
        help_text=_("Time box, between 20 and 60 minutes"),
    )
    expected_time_minutes = models.PositiveIntegerField(
        help_text=_(
            "Authored estimate at roughly 60-70% of the limit. The slack is where "
            "writing NOTES.md is meant to happen"
        ),
    )

    # NOTE: optional JSON fields need blank=True as well as a default. Without it
    # full_clean() rejects an empty list as "blank", which would make these
    # unsavable from the admin. definition_of_done and protected_paths are
    # deliberately left strict, because an exercise without them is not gradeable.
    focus_paths = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Where the work belongs; orders the diff sent to the grader"),
    )
    protected_paths = models.JSONField(
        default=list,
        help_text=_("Globs hashed at scaffold time so test tampering is detectable"),
    )
    mutations = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Typed operations that break the pristine template"),
    )
    grading_spec = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Authored checks, weights and the measured pre-fix baseline"),
    )
    grading_notes = models.TextField(
        blank=True,
        help_text=_(
            "PRIVATE. Root cause, what a good fix looks like, and common wrong turns. "
            "Sent to the grader but never shown to the user"
        ),
    )
    context_excerpts = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Unchanged code the grader needs in order to judge fit with the codebase"),
    )
    hints = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Progressive hints; each one costs engineering points"),
    )

    databases = models.JSONField(
        default=list,
        blank=True,
        help_text=_(
            "Subset of postgres/mongodb/duckdb. RDS is emulated as Postgres plus "
            "RDS-shaped artifacts in config, not a distinct backend"
        ),
    )
    needs_docker = models.BooleanField(
        default=True, help_text=_("Whether the exercise requires containers to run")
    )
    template_dir = models.CharField(
        max_length=120,
        blank=True,
        help_text=_("Directory under WORKSPACE_TEMPLATE_ROOT; defaults to base_app"),
    )
    template_checksum = models.CharField(
        max_length=64,
        blank=True,
        help_text=_("SHA-256 over the template tree, to detect unintended edits"),
    )

    primary_subject = models.ForeignKey(
        "subjects.Subject",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="workspace_exercises",
        help_text=_(
            "For filtering and discovery only. Nothing aggregates by this, which is "
            "what keeps subject dashboards meaningful"
        ),
    )
    tags = models.JSONField(default=list, blank=True, help_text=_("Free-form catalog tags"))
    is_active = models.BooleanField(
        default=True, db_index=True, help_text=_("Whether the exercise appears in the catalog")
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["exercise_number"]
        verbose_name = _("workspace exercise")
        verbose_name_plural = _("workspace exercises")
        indexes = [
            models.Index(fields=["exercise_type", "difficulty", "is_active"]),
            models.Index(fields=["base_app", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.exercise_number:03d}. {self.title}"

    def save(self, *args, **kwargs) -> None:
        """Default ``template_dir`` to the base app before saving."""
        if not self.template_dir:
            self.template_dir = self.base_app
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        """Return the exercise detail page URL."""
        return reverse("workspace:exercise", kwargs={"slug": self.slug})

    @property
    def time_limit_minutes(self) -> int:
        """The time limit in whole minutes, for display."""
        return self.time_limit_seconds // 60


class WorkspaceSession(models.Model):
    """One user's attempt at one exercise."""

    class Status(models.TextChoices):
        """Lifecycle of an attempt.

        ``SCAFFOLDING`` and ``READY`` are both **before the clock starts**, which is
        what keeps container bring-up and dependency installation off the time box.
        """

        SCAFFOLDING = "scaffolding", _("Scaffolding")
        READY = "ready", _("Ready to start")
        IN_PROGRESS = "in_progress", _("In progress")
        GRADING = "grading", _("Grading")
        COMPLETED = "completed", _("Completed")
        TIMED_OUT = "timed_out", _("Timed out")
        ABANDONED = "abandoned", _("Abandoned")
        FAILED = "failed", _("Failed to set up")

    class EndReason(models.TextChoices):
        """Why an attempt ended."""

        SUBMITTED = "submitted", _("Submitted")
        TIMED_OUT = "timed_out", _("Ran out of time")
        ABANDONED = "abandoned", _("Abandoned by the user")
        REAPED = "reaped", _("Closed automatically after the deadline")
        FAILED = "failed", _("Setup failed")

    #: Statuses in which the session is still live and its directory must not be
    #: touched by cleanup.
    ACTIVE_STATUSES = (
        Status.SCAFFOLDING,
        Status.READY,
        Status.IN_PROGRESS,
        Status.GRADING,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workspace_sessions"
    )
    exercise = models.ForeignKey(
        WorkspaceExercise,
        on_delete=models.PROTECT,
        related_name="sessions",
        help_text=_("PROTECT so a graded attempt is never orphaned by a catalog edit"),
    )

    # Snapshots taken at session creation. Exercise rows are editable, and a
    # session must be able to reproduce the conditions it was actually run under.
    exercise_type = models.CharField(max_length=30, choices=ExerciseType.choices)
    difficulty = models.CharField(max_length=20, choices=Difficulty.choices)
    time_limit_seconds = models.PositiveIntegerField(
        validators=[
            MinValueValidator(settings.WORKSPACE_MIN_TIME_LIMIT_SECONDS),
            MaxValueValidator(settings.WORKSPACE_MAX_TIME_LIMIT_SECONDS),
        ],
        help_text=_("Snapshot of the exercise's limit; the progress bar denominator"),
    )
    template_checksum = models.CharField(max_length=64, blank=True)

    # On-disk state.
    workspace_path = models.CharField(
        max_length=500, blank=True, help_text=_("Absolute path to the scaffolded repository")
    )
    sentinel_written = models.BooleanField(
        default=False,
        help_text=_("Whether the deletion-guard sentinel file was written successfully"),
    )
    seed_commit_sha = models.CharField(
        max_length=40,
        blank=True,
        help_text=_("The scaffold commit; the base for every diff taken at submit time"),
    )
    origin_path = models.CharField(
        max_length=500,
        blank=True,
        help_text=_("Bare repository that emulates GitHub for push/pull/fetch"),
    )
    compose_project = models.CharField(
        max_length=64,
        blank=True,
        help_text=_("COMPOSE_PROJECT_NAME, isolating this exercise's containers"),
    )
    host_ports = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Service name to allocated host port, e.g. {'postgres': 55123}"),
    )
    scaffold_log = models.TextField(
        blank=True, help_text=_("Step-by-step scaffolding log, shown to the user on failure")
    )

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SCAFFOLDING, db_index=True
    )
    end_reason = models.CharField(max_length=20, choices=EndReason.choices, blank=True)

    started_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_(
            "Set explicitly when the user starts the clock, NOT on row creation, so "
            "scaffolding and container startup do not consume the time box"
        ),
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Absolute deadline. The authority for all time enforcement"),
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    user_notes = models.TextField(
        blank=True,
        help_text=_("The NOTES.md-style writeup, autosaved and sent to the grader"),
    )
    hints_used = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("workspace session")
        verbose_name_plural = _("workspace sessions")
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "expires_at"]),
        ]
        constraints = [
            # Two live sessions on one exercise would target the same directory.
            # Enforced in the database rather than only in the view.
            models.UniqueConstraint(
                fields=["user", "exercise"],
                condition=models.Q(
                    status__in=[
                        "scaffolding",
                        "ready",
                        "in_progress",
                        "grading",
                    ]
                ),
                name="one_active_workspace_session_per_exercise",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} - {self.exercise.slug} ({self.status})"

    def get_absolute_url(self) -> str:
        """Return the URL for whichever page suits the current status."""
        if self.status == self.Status.SCAFFOLDING or self.status == self.Status.READY:
            return reverse("workspace:prepare", kwargs={"pk": self.pk})
        if self.status == self.Status.IN_PROGRESS:
            return reverse("workspace:session", kwargs={"pk": self.pk})
        return self.get_results_url()

    def get_results_url(self) -> str:
        """Return the results page URL."""
        return reverse("workspace:results", kwargs={"pk": self.pk})

    # -- timer ------------------------------------------------------------

    @property
    def time_remaining_seconds(self) -> int:
        """Seconds left before the deadline, or 0 if not currently running."""
        if self.status != self.Status.IN_PROGRESS or self.expires_at is None:
            return 0
        return max(0, int((self.expires_at - timezone.now()).total_seconds()))

    @property
    def is_time_up(self) -> bool:
        """Whether the deadline has passed.

        Deliberately **not** derived from :attr:`time_remaining_seconds`.
        ``apps/lightning``'s equivalent returns ``True`` for an already-completed
        session, which forces every caller to add ``and status == IN_PROGRESS``
        (see ``apps/systemdesign/views.py``). This anchors on the deadline alone,
        so the two concepts stay independent.
        """
        if self.expires_at is None:
            return False
        return timezone.now() >= self.expires_at

    @property
    def is_past_grace(self) -> bool:
        """Whether the submit grace period has also elapsed.

        A submit fired two seconds before the bell whose capture takes six seconds
        must still be accepted.
        """
        if self.expires_at is None:
            return False
        grace = timedelta(seconds=settings.WORKSPACE_SUBMIT_GRACE_SECONDS)
        return timezone.now() >= self.expires_at + grace

    @property
    def elapsed_seconds(self) -> int:
        """Seconds since the clock started, or 0 if it has not."""
        if self.started_at is None:
            return 0
        end = self.submitted_at or self.completed_at or timezone.now()
        return max(0, int((end - self.started_at).total_seconds()))

    @property
    def fraction_time_used(self) -> float:
        """Proportion of the time box consumed, clamped to 0.0-1.0.

        Feeds the A+ gate and the speed bonus in :mod:`apps.workspace.grading`.
        """
        if not self.time_limit_seconds:
            return 1.0
        return max(0.0, min(1.0, self.elapsed_seconds / self.time_limit_seconds))

    @property
    def time_used_percentage(self) -> int:
        """Proportion of the time box consumed, as a whole percentage."""
        return int(round(self.fraction_time_used * 100))

    @property
    def is_active(self) -> bool:
        """Whether this session still owns its workspace directory."""
        return self.status in self.ACTIVE_STATUSES

    def begin(self, *, now=None) -> None:
        """Start the clock and move the session to in-progress.

        Called from the prepare page once the user has their environment up, which
        is what keeps setup time off the clock.

        Args:
            now: Override for the start instant; defaults to the current time.
        """
        moment = now or timezone.now()
        self.started_at = moment
        self.expires_at = moment + timedelta(seconds=self.time_limit_seconds)
        self.status = self.Status.IN_PROGRESS
        self.save(update_fields=["started_at", "expires_at", "status"])

    def end_session(self, reason: str, *, now=None) -> None:
        """End the attempt and record why.

        Args:
            reason: A :class:`EndReason` value.
            now: Override for the end instant; defaults to the current time.
        """
        moment = now or timezone.now()
        self.end_reason = reason
        if reason == self.EndReason.ABANDONED:
            self.status = self.Status.ABANDONED
        elif reason in {self.EndReason.TIMED_OUT, self.EndReason.REAPED}:
            self.status = self.Status.TIMED_OUT
        elif reason == self.EndReason.FAILED:
            self.status = self.Status.FAILED
        else:
            self.status = self.Status.COMPLETED
        self.completed_at = moment
        self.save(update_fields=["end_reason", "status", "completed_at"])


class WorkspaceSubmission(models.Model):
    """The work captured from a workspace at submit time.

    Committed to the database *before* grading is enqueued, so a grading failure
    never loses the user's work and a regrade can reuse the exact same bytes.
    """

    session = models.OneToOneField(
        WorkspaceSession, on_delete=models.CASCADE, related_name="submission"
    )
    captured_at = models.DateTimeField(auto_now_add=True)
    capture_ok = models.BooleanField(
        default=True, help_text=_("False when the workspace was missing or unreadable")
    )
    capture_error = models.TextField(blank=True)

    snapshot_ref = models.CharField(max_length=120, blank=True)
    snapshot_sha = models.CharField(max_length=40, blank=True)

    diff_text = models.TextField(blank=True, help_text=_("The primary grading artifact"))
    diff_numstat = models.JSONField(
        default=list,
        blank=True,
        help_text=_(
            "Complete inventory of changed files. Never truncated, so the grader "
            "always knows what it did not see"
        ),
    )
    full_files = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Whole-file contents for paths grading needs in full"),
    )

    files_changed = models.PositiveIntegerField(default=0)
    lines_added = models.PositiveIntegerField(default=0)
    lines_deleted = models.PositiveIntegerField(default=0)

    git_log = models.TextField(
        blank=True, help_text=_("Commits since the seed, with full bodies not just subjects")
    )
    user_commit_count = models.PositiveIntegerField(default=0)
    branches = models.JSONField(default=list, blank=True)
    porcelain_status = models.TextField(blank=True)
    untracked_paths = models.JSONField(default=list, blank=True)

    bundle_path = models.CharField(
        max_length=500, blank=True, help_text=_("Archived git bundle of the whole attempt")
    )
    capture_bytes = models.PositiveIntegerField(default=0)
    truncated = models.BooleanField(
        default=False, help_text=_("Whether the diff was trimmed to fit the grading prompt")
    )
    truncation_report = models.JSONField(default=dict, blank=True)
    prompt_char_count = models.PositiveIntegerField(default=0)
    sections_truncated = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-captured_at"]
        verbose_name = _("workspace submission")
        verbose_name_plural = _("workspace submissions")

    def __str__(self) -> str:
        return f"Submission for session {self.session_id} ({self.files_changed} files)"

    @property
    def is_empty(self) -> bool:
        """Whether nothing was submitted at all.

        Drives the empty-submission grading gate. Note that working in a dirty tree
        without committing still counts as work.
        """
        return self.files_changed == 0 and self.user_commit_count == 0


class WorkspaceCheckResult(models.Model):
    """The outcome of one objective acceptance check."""

    submission = models.ForeignKey(
        WorkspaceSubmission, on_delete=models.CASCADE, related_name="check_results"
    )
    check_id = models.CharField(max_length=60, help_text=_("Authored id, e.g. 'R1' or 'S2'"))
    kind = models.CharField(max_length=20, choices=CheckKind.choices)
    status = models.CharField(max_length=10, choices=CheckStatus.choices, db_index=True)
    passed = models.BooleanField(default=False)

    weight = models.PositiveIntegerField(default=1)
    required = models.BooleanField(default=True)
    stretch = models.BooleanField(
        default=False, help_text=_("Passing at least one stretch check is required for A+")
    )

    expected = models.TextField(blank=True)
    actual = models.TextField(blank=True)
    description = models.TextField(blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    output = models.TextField(blank=True, help_text=_("Truncated raw command output"))

    class Meta:
        ordering = ["-required", "check_id"]
        verbose_name = _("workspace check result")
        verbose_name_plural = _("workspace check results")
        indexes = [models.Index(fields=["submission", "passed"])]
        constraints = [
            models.UniqueConstraint(
                fields=["submission", "check_id"], name="unique_check_per_submission"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.check_id}: {self.status}"

    @property
    def ran(self) -> bool:
        """Whether the check produced a real verdict rather than failing to run."""
        return self.status in {CheckStatus.PASSED, CheckStatus.FAILED}


class WorkspaceGrade(models.Model):
    """The final grade for a submission.

    ``overall_score`` keeps the project's 0-100 convention so cross-mode
    aggregates still work, while ``letter_grade`` carries the user-facing result
    and ``grade_points`` allows averaging without sorting strings.
    """

    session = models.OneToOneField(WorkspaceSession, on_delete=models.CASCADE, related_name="grade")

    overall_score = models.PositiveSmallIntegerField(
        validators=[MaxValueValidator(100)],
        help_text=_("Weighted 0-100 score, after any speed bonus"),
    )
    base_score = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(100)], help_text=_("Before any bonus")
    )
    letter_grade = models.CharField(
        max_length=2, choices=LetterGrade.choices, blank=True, db_index=True
    )
    uncapped_letter = models.CharField(
        max_length=2,
        choices=LetterGrade.choices,
        blank=True,
        help_text=_("What the numeric score alone would have earned"),
    )
    grade_points = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("4.0-scale value, so progress can be averaged numerically"),
    )

    dimension_scores = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("correctness / engineering / documentation / completeness, each 0-100"),
    )
    documentation_breakdown = models.JSONField(
        default=dict, blank=True, help_text=_("The five documentation sub-scores")
    )
    applied_caps = models.JSONField(
        default=list,
        blank=True,
        help_text=_(
            "Gate codes that lowered the grade. Shown to the user, because a letter "
            "without its explanation reads as arbitrary"
        ),
    )
    applied_deductions = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Objective deductions applied to engineering quality"),
    )
    speed_bonus = models.PositiveSmallIntegerField(default=0)

    objective_status = models.CharField(
        max_length=20,
        choices=ObjectiveStatus.choices,
        default=ObjectiveStatus.INDETERMINATE,
        help_text=_("Whether the machine-checked half of the grade could be determined"),
    )
    evaluation_degraded = models.BooleanField(
        default=False,
        help_text=_("True when model review was unavailable and the grade is provisional"),
    )

    summary_feedback = models.TextField(blank=True)
    detailed_feedback = models.TextField(blank=True)
    strengths = models.JSONField(default=list, blank=True)
    areas_for_improvement = models.JSONField(default=list, blank=True)
    what_a_senior_would_have_done = models.TextField(blank=True)
    root_cause_summary = models.TextField(blank=True)
    symptom_patch_suspected = models.BooleanField(default=False)

    rubric_version = models.CharField(max_length=20, blank=True)
    model_used = models.CharField(max_length=60, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    grading_log = models.TextField(
        blank=True, help_text=_("Every command the harness ran, for auditability")
    )
    grading_error = models.TextField(blank=True)
    graded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-graded_at"]
        verbose_name = _("workspace grade")
        verbose_name_plural = _("workspace grades")

    def __str__(self) -> str:
        return f"{self.letter_grade or '?'} ({self.overall_score}) for session {self.session_id}"

    @property
    def was_capped(self) -> bool:
        """Whether a gate lowered the grade below its numeric score."""
        return bool(self.applied_caps)


class WorkspaceEvent(models.Model):
    """Audit trail for a session.

    The only practical way to answer "the timer was wrong" or "my directory
    vanished" after the fact.
    """

    class Kind(models.TextChoices):
        """What happened."""

        SCAFFOLD_STARTED = "scaffold_started", _("Scaffold started")
        SCAFFOLD_OK = "scaffold_ok", _("Scaffold succeeded")
        SCAFFOLD_FAILED = "scaffold_failed", _("Scaffold failed")
        CONTAINERS_UP = "containers_up", _("Containers started")
        CONTAINERS_FAILED = "containers_failed", _("Containers failed to start")
        BEGUN = "begun", _("Clock started")
        HINT_REVEALED = "hint_revealed", _("Hint revealed")
        WORKSPACE_MISSING = "workspace_missing", _("Workspace directory missing")
        DOCKER_MISSING = "docker_missing", _("Docker unavailable")
        SUBMITTED = "submitted", _("Submitted")
        TIMED_OUT = "timed_out", _("Timed out")
        REAPED = "reaped", _("Reaped after the deadline")
        GRADED = "graded", _("Graded")
        GRADE_FAILED = "grade_failed", _("Grading failed")
        TORN_DOWN = "torn_down", _("Workspace torn down")

    session = models.ForeignKey(WorkspaceSession, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=30, choices=Kind.choices, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("workspace event")
        verbose_name_plural = _("workspace events")
        indexes = [models.Index(fields=["session", "kind"])]

    def __str__(self) -> str:
        return f"{self.kind} @ {self.created_at:%Y-%m-%d %H:%M:%S}"

    @classmethod
    def log(cls, session: WorkspaceSession, kind: str, **payload) -> WorkspaceEvent:
        """Record an event.

        Args:
            session: The session the event belongs to.
            kind: A :class:`Kind` value.
            **payload: Arbitrary JSON-serialisable detail.

        Returns:
            The created event.
        """
        return cls.objects.create(session=session, kind=kind, payload=payload)
