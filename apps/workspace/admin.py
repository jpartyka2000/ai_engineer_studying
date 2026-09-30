"""Admin registrations for workspace mode.

Exercises are editable, because they are authored content. Everything downstream
of a session -- the session itself, its submission, checks, grade and events -- is
**read-only**, because those records are evidence of an attempt. Letting them be
hand-edited would quietly destroy the audit trail that makes a letter grade
defensible.
"""

from pathlib import Path

from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.workspace.models import (
    WorkspaceCheckResult,
    WorkspaceEvent,
    WorkspaceExercise,
    WorkspaceGrade,
    WorkspaceSession,
    WorkspaceSubmission,
)


class ReadOnlyInline(admin.TabularInline):
    """An inline that can be read but never added to, edited or deleted."""

    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None) -> bool:  # noqa: D102
        return False

    def has_change_permission(self, request, obj=None) -> bool:  # noqa: D102
        return False


class WorkspaceEventInline(ReadOnlyInline):
    """Timeline of what happened during a session."""

    model = WorkspaceEvent
    fields = ("created_at", "kind", "payload")
    readonly_fields = fields
    ordering = ("created_at",)


class WorkspaceCheckResultInline(ReadOnlyInline):
    """Per-check outcomes for a submission."""

    model = WorkspaceCheckResult
    fields = ("check_id", "kind", "status", "required", "stretch", "weight", "actual")
    readonly_fields = fields


@admin.register(WorkspaceExercise)
class WorkspaceExerciseAdmin(admin.ModelAdmin):
    """Authoring interface for the exercise catalog."""

    list_display = (
        "exercise_number",
        "title",
        "exercise_type",
        "base_app",
        "difficulty",
        "time_limit_minutes",
        "defect_class",
        "is_active",
    )
    list_filter = ("exercise_type", "base_app", "difficulty", "is_active", "needs_docker")
    search_fields = ("slug", "title", "defect_class", "tags")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("template_checksum", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("exercise_number", "slug", "title", "is_active")}),
        (
            _("Classification"),
            {"fields": ("exercise_type", "base_app", "difficulty", "defect_class", "tags")},
        ),
        (
            _("Brief and time box"),
            {
                "fields": (
                    "brief_md",
                    "definition_of_done",
                    "time_limit_seconds",
                    "expected_time_minutes",
                )
            },
        ),
        (
            _("Grading (private)"),
            {
                "fields": ("grading_spec", "grading_notes", "context_excerpts", "hints"),
                "description": _(
                    "grading_notes is sent to the grader but never shown to the user."
                ),
            },
        ),
        (
            _("Template and environment"),
            {
                "fields": (
                    "template_dir",
                    "template_checksum",
                    "focus_paths",
                    "protected_paths",
                    "mutations",
                    "databases",
                    "needs_docker",
                )
            },
        ),
        (_("Discovery"), {"fields": ("primary_subject",)}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description=_("Limit"), ordering="time_limit_seconds")
    def time_limit_minutes(self, obj: WorkspaceExercise) -> str:
        """Show the time box in minutes."""
        return f"{obj.time_limit_minutes} min"


@admin.register(WorkspaceSession)
class WorkspaceSessionAdmin(admin.ModelAdmin):
    """Read-only view of attempts, with a teardown escape hatch."""

    list_display = (
        "pk",
        "user",
        "exercise",
        "status",
        "end_reason",
        "letter",
        "time_remaining_display",
        "workspace_exists",
        "created_at",
    )
    list_filter = ("status", "end_reason", "exercise_type", "difficulty")
    search_fields = ("user__username", "exercise__slug", "workspace_path")
    list_select_related = ("user", "exercise")
    inlines = (WorkspaceEventInline,)
    date_hierarchy = "created_at"
    actions = ("terminate_and_teardown",)

    def get_readonly_fields(self, request, obj=None) -> tuple[str, ...]:
        """Every field is read-only: these records are evidence, not data entry."""
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request) -> bool:
        """Sessions are only ever created by starting an exercise."""
        return False

    @admin.display(description=_("Grade"))
    def letter(self, obj: WorkspaceSession) -> str:
        """Show the letter grade, if the attempt has been graded."""
        grade = getattr(obj, "grade", None)
        if grade is None:
            return "-"
        return f"{grade.letter_grade} ({grade.overall_score})"

    @admin.display(description=_("Remaining"))
    def time_remaining_display(self, obj: WorkspaceSession) -> str:
        """Show remaining time for a running attempt."""
        if obj.status != WorkspaceSession.Status.IN_PROGRESS:
            return "-"
        remaining = obj.time_remaining_seconds
        return f"{remaining // 60:d}:{remaining % 60:02d}"

    @admin.display(description=_("On disk"), boolean=True)
    def workspace_exists(self, obj: WorkspaceSession) -> bool:
        """Whether the scaffolded directory is still present."""
        return bool(obj.workspace_path) and Path(obj.workspace_path).is_dir()

    @admin.action(description=_("Terminate and tear down the workspace"))
    def terminate_and_teardown(self, request, queryset) -> None:
        """Force-end selected sessions and remove their directories.

        The escape hatch for a session that has wedged. Deletion still goes through
        the sentinel-gated path kernel, so a directory this app did not create is
        left alone even here.
        """
        from apps.workspace.services import reaper

        ended = 0
        failures: list[str] = []
        for session in queryset:
            try:
                reaper.teardown(session, reason=WorkspaceSession.EndReason.ABANDONED)
                ended += 1
            except Exception as exc:  # noqa: BLE001 - surfaced to the admin user
                failures.append(f"session {session.pk}: {exc}")

        if ended:
            self.message_user(request, _("Tore down %(n)d session(s).") % {"n": ended})
        for failure in failures:
            self.message_user(request, failure, level=messages.ERROR)


@admin.register(WorkspaceSubmission)
class WorkspaceSubmissionAdmin(admin.ModelAdmin):
    """Read-only view of captured work, for debugging truncation."""

    list_display = (
        "pk",
        "session",
        "captured_at",
        "capture_ok",
        "files_changed",
        "lines_added",
        "lines_deleted",
        "user_commit_count",
        "truncated",
    )
    list_filter = ("capture_ok", "truncated")
    search_fields = ("session__user__username", "session__exercise__slug")
    list_select_related = ("session",)
    inlines = (WorkspaceCheckResultInline,)

    def get_readonly_fields(self, request, obj=None) -> tuple[str, ...]:  # noqa: D102
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request) -> bool:  # noqa: D102
        return False


@admin.register(WorkspaceGrade)
class WorkspaceGradeAdmin(admin.ModelAdmin):
    """Read-only view of grades, including which gates were applied."""

    list_display = (
        "pk",
        "session",
        "letter_badge",
        "overall_score",
        "uncapped_letter",
        "objective_status",
        "evaluation_degraded",
        "graded_at",
    )
    list_filter = ("letter_grade", "objective_status", "evaluation_degraded")
    search_fields = ("session__user__username", "session__exercise__slug")
    list_select_related = ("session",)

    def get_readonly_fields(self, request, obj=None) -> tuple[str, ...]:  # noqa: D102
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request) -> bool:  # noqa: D102
        return False

    @admin.display(description=_("Letter"), ordering="letter_grade")
    def letter_badge(self, obj: WorkspaceGrade) -> str:
        """Show the letter, flagged when a gate capped it."""
        if obj.was_capped:
            return format_html(
                '<strong>{}</strong> <span style="color:#b45309">(capped)</span>',
                obj.letter_grade or "?",
            )
        return format_html("<strong>{}</strong>", obj.letter_grade or "?")


@admin.register(WorkspaceEvent)
class WorkspaceEventAdmin(admin.ModelAdmin):
    """Read-only audit trail, searchable across sessions."""

    list_display = ("pk", "session", "kind", "created_at")
    list_filter = ("kind",)
    search_fields = ("session__user__username", "session__exercise__slug")
    list_select_related = ("session",)
    date_hierarchy = "created_at"

    def get_readonly_fields(self, request, obj=None) -> tuple[str, ...]:  # noqa: D102
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request) -> bool:  # noqa: D102
        return False
