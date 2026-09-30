"""Pydantic schemas for workspace mode.

Three groups live here:

* **Evaluation** -- the shape the grading model must return. Modelled on
  ``apps/coding/schemas.py`` but with documentation as a first-class dimension
  and, deliberately, **no** ``overall_score`` field (see :class:`ExerciseEvaluation`).
* **Manifest** -- the authored ``manifest.json`` shipped with each base app.
* **Authored catalog** -- validation for the 50 exercise definitions, so a bad
  entry fails at seed time rather than reaching the database.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from apps.workspace.enums import (
    BaseApp,
    CheckKind,
    Database,
    Difficulty,
    ExerciseType,
)

# ---------------------------------------------------------------------------
# Evaluation (the grading model's response)
# ---------------------------------------------------------------------------


class EvaluationCategory(BaseModel):
    """A single scored rubric dimension. Mirrors ``apps/coding``'s shape."""

    score: int = Field(ge=0, le=100)
    feedback: str


class DocumentationBreakdown(BaseModel):
    """Sub-scores for the documentation dimension.

    Broken out so the 25% documentation weight is reproducible rather than a
    single holistic impression, and so feedback can point at what was missing.
    """

    inline_comments: int = Field(ge=0, le=100)
    docstrings: int = Field(ge=0, le=100)
    commit_messages: int = Field(ge=0, le=100)
    writeup_notes_md: int = Field(ge=0, le=100)
    updated_project_docs: int = Field(ge=0, le=100)


class AcceptanceJudgment(BaseModel):
    """A verdict on one acceptance criterion that has no mechanical check."""

    criterion_id: str
    met: bool
    confidence: Literal["low", "medium", "high"]
    rationale: str


class ExerciseEvaluation(BaseModel):
    """The grading model's full response.

    Deliberately omits ``overall_score`` and any authoritative ``is_correct``.
    In ``apps/coding`` the model returns ``overall_score`` which the service then
    silently recomputes whenever tests ran, leaving a dead and confusing field.
    Here the weighted score is *always* computed in Python
    (:mod:`apps.workspace.grading`); the model never produces the final number.
    """

    solved: bool = Field(description="Advisory only; objective checks are authoritative")
    root_cause_identified: bool
    root_cause_summary: str

    #: The key anti-gaming signal: tests pass but the implementation is a cheat.
    symptom_patch_suspected: bool = False

    correctness: EvaluationCategory
    engineering_quality: EvaluationCategory
    documentation: EvaluationCategory
    documentation_breakdown: DocumentationBreakdown
    completeness: EvaluationCategory

    acceptance_judgments: list[AcceptanceJudgment] = Field(default_factory=list)
    stretch_criteria_met: list[str] = Field(default_factory=list)

    summary_feedback: str
    detailed_feedback: str
    strengths: list[str] = Field(default_factory=list)
    areas_for_improvement: list[str] = Field(default_factory=list)

    #: The teaching payload: what a senior engineer would have done differently.
    what_a_senior_would_have_done: str = ""


# ---------------------------------------------------------------------------
# Manifest (authored per base app)
# ---------------------------------------------------------------------------


class SeedCommit(BaseModel):
    """One commit in an exercise's fabricated git history.

    Backdated and attributed to a plausible author, because making ``git log``
    and ``git bisect`` genuinely useful is a large part of the point of this mode.
    """

    message: str
    author: str = "Dev Team <dev@example.com>"
    date: str
    paths: list[str] = Field(min_length=1)


class SeedBranch(BaseModel):
    """An extra branch to create, pointing at one of the seed commits."""

    name: str
    from_commit_index: int = Field(ge=0)


class EnvSpec(BaseModel):
    """What the generated ``.env`` must contain."""

    required: list[str] = Field(default_factory=list)
    extra: dict[str, str] = Field(default_factory=dict)
    requires_anthropic_key: bool = False


class GradingSpec(BaseModel):
    """Manifest-level hints for assembling the grading prompt."""

    diff_exclude: list[str] = Field(default_factory=list)
    include_full_files: list[str] = Field(default_factory=list)


class Manifest(BaseModel):
    """A base app's ``manifest.json``."""

    schema_version: int = 1
    seed_commits: list[SeedCommit] = Field(min_length=1)
    seed_branches: list[SeedBranch] = Field(default_factory=list)
    env: EnvSpec = Field(default_factory=EnvSpec)
    #: Service name -> in-container port, e.g. ``{"postgres": 5432}``.
    ports: dict[str, int] = Field(default_factory=dict)
    #: Service name -> path under the template holding seed SQL/JS/scripts.
    db_seeds: dict[str, str] = Field(default_factory=dict)
    #: Copy-pasteable setup steps shown on the (off-the-clock) prepare page.
    setup_commands: list[str] = Field(default_factory=list)
    grading: GradingSpec = Field(default_factory=GradingSpec)

    @model_validator(mode="after")
    def _branches_reference_real_commits(self) -> Manifest:
        """Reject a branch pointing past the end of the seed history."""
        for branch in self.seed_branches:
            if branch.from_commit_index >= len(self.seed_commits):
                raise ValueError(
                    f"seed branch {branch.name!r} references commit index "
                    f"{branch.from_commit_index} but only {len(self.seed_commits)} "
                    "seed commits are defined"
                )
        return self


# ---------------------------------------------------------------------------
# Authored catalog (the 50 exercise definitions)
# ---------------------------------------------------------------------------


class Check(BaseModel):
    """One objective acceptance check.

    ``required`` checks drive the correctness score and the unsolved gate.
    ``stretch`` checks are what a strong engineer does unprompted, and passing at
    least one is a precondition for A+.
    """

    id: str = Field(min_length=1)
    kind: CheckKind
    #: Meaning depends on ``kind``: a pytest node id, a command, a file glob, a
    #: benchmark script path, a regex.
    target: str = ""
    #: Metric comparison for benchmark/metric checks, e.g.
    #: ``{"metric": "queries", "op": "<=", "threshold": 5}``.
    expect: dict[str, Any] = Field(default_factory=dict)
    paths: list[str] = Field(default_factory=list)
    weight: int = Field(default=1, ge=0)
    required: bool = True
    stretch: bool = False
    #: Number of repetitions for ``flake_repeat``.
    repeat: int = Field(default=1, ge=1)
    description: str = ""

    @model_validator(mode="after")
    def _required_and_stretch_are_exclusive(self) -> Check:
        if self.required and self.stretch:
            raise ValueError(f"check {self.id!r} cannot be both required and stretch")
        return self

    @model_validator(mode="after")
    def _file_unchanged_needs_paths(self) -> Check:
        if self.kind == CheckKind.FILE_UNCHANGED and not self.paths:
            raise ValueError(f"check {self.id!r} is file_unchanged but lists no paths")
        return self

    @model_validator(mode="after")
    def _threshold_checks_need_an_expectation(self) -> Check:
        if self.kind in {CheckKind.BENCHMARK, CheckKind.METRIC}:
            missing = {"metric", "op", "threshold"} - set(self.expect)
            if missing:
                raise ValueError(
                    f"check {self.id!r} of kind {self.kind} is missing "
                    f"expect keys: {sorted(missing)}"
                )
        return self


class Baseline(BaseModel):
    """The measured pre-fix state of an exercise.

    Recorded by the verification harness rather than guessed, and asserted for
    **exact set equality** during verification: a superset of failing tests means
    the injected defect broke more than intended, which makes the exercise unfair
    and renders the regression check meaningless.
    """

    failing_nodes: list[str] = Field(default_factory=list)
    passing_nodes: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)


class ContextExcerpt(BaseModel):
    """A snippet of *unchanged* code the reviewer needs in order to judge fit.

    For example, the existing ``TenantScopedQuerySet`` a good fix should have
    reused. Without these the model cannot tell idiomatic work from a bolt-on.
    """

    path: str
    line_range: str = ""
    why: str = ""


class AuthoredExercise(BaseModel):
    """One of the 50 authored exercise definitions.

    Validated at seed time so a malformed entry fails loudly instead of landing
    in the database.
    """

    slug: str = Field(min_length=1)
    exercise_number: int = Field(ge=1, le=999)
    title: str = Field(min_length=1)
    exercise_type: ExerciseType
    base_app: BaseApp
    difficulty: Difficulty
    defect_class: str = Field(min_length=1)

    time_limit_minutes: int = Field(ge=20, le=60)
    expected_time_minutes: int = Field(ge=1)

    brief_md: str = Field(min_length=1)
    definition_of_done: list[str] = Field(min_length=1)

    focus_paths: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)
    mutations: list[dict[str, Any]] = Field(default_factory=list)
    checks: list[Check] = Field(min_length=1)
    baseline: Baseline = Field(default_factory=Baseline)

    grading_notes: str = ""
    context_excerpts: list[ContextExcerpt] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list)

    databases: list[Database] = Field(default_factory=list)
    needs_docker: bool = True
    tags: list[str] = Field(default_factory=list)

    @field_validator("slug")
    @classmethod
    def _slug_is_url_safe(cls, value: str) -> str:
        if not all(ch.isalnum() or ch in "-_" for ch in value):
            raise ValueError(f"slug {value!r} must contain only alphanumerics, - and _")
        return value

    @model_validator(mode="after")
    def _expected_time_fits_the_box(self) -> AuthoredExercise:
        """The expected time must leave slack -- that slack is where docs happen."""
        if self.expected_time_minutes > self.time_limit_minutes:
            raise ValueError(
                f"{self.slug}: expected_time_minutes ({self.expected_time_minutes}) "
                f"exceeds time_limit_minutes ({self.time_limit_minutes})"
            )
        return self

    @model_validator(mode="after")
    def _has_at_least_one_stretch_check(self) -> AuthoredExercise:
        """Without a stretch check, A+ would be unreachable for this exercise."""
        if not any(check.stretch for check in self.checks):
            raise ValueError(
                f"{self.slug}: at least one stretch check is required, otherwise "
                "A+ is unreachable (see grading gate G7)"
            )
        return self

    @model_validator(mode="after")
    def _has_at_least_one_required_check(self) -> AuthoredExercise:
        if not any(check.required for check in self.checks):
            raise ValueError(f"{self.slug}: at least one required check is needed")
        return self

    @model_validator(mode="after")
    def _check_ids_are_unique(self) -> AuthoredExercise:
        seen = [check.id for check in self.checks]
        duplicates = {cid for cid in seen if seen.count(cid) > 1}
        if duplicates:
            raise ValueError(f"{self.slug}: duplicate check ids {sorted(duplicates)}")
        return self

    @model_validator(mode="after")
    def _done_items_map_to_checks_or_judgment(self) -> AuthoredExercise:
        """Every Definition of Done item must be gradeable.

        An item is gradeable if it names a real check id or the literal ``"llm"``.
        Without this, a brief can promise something the grader never looks at.
        """
        known = {check.id for check in self.checks} | {"llm"}
        # Items are authored as "check_id: human text" or "llm: human text".
        for item in self.definition_of_done:
            key = item.split(":", 1)[0].strip()
            if key not in known:
                raise ValueError(
                    f"{self.slug}: definition_of_done item {item!r} does not start "
                    f"with a known check id or 'llm' (known: {sorted(known)})"
                )
        return self

    @model_validator(mode="after")
    def _protected_paths_cover_test_dirs(self) -> AuthoredExercise:
        """Fix-type exercises must protect their proving tests.

        Without this, the cheapest way to pass is to edit the test -- and the
        tampering gate would have nothing to detect.
        """
        if not self.protected_paths:
            raise ValueError(
                f"{self.slug}: protected_paths must list the test/fixture files "
                "that prove the fix, so tampering is detectable"
            )
        return self
