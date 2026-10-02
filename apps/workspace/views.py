"""Views for workspace mode.

The browser is deliberately a thin shell: it shows the brief, the countdown, a
read-only file tree, and a submit button. All the real work happens in the user's own
terminal, editor and browser against a directory on disk — which is what makes "run
any program installed on my machine" literally true rather than approximately true.

Time enforcement happens on the server at five points, listed in
:func:`_enforce_deadline`'s docstring. The client countdown is cosmetic.
"""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import DetailView, ListView

from apps.workspace.enums import GradeFairness
from apps.workspace.exceptions import UnsafePathError, WorkspaceError
from apps.workspace.models import (
    WorkspaceEvent,
    WorkspaceExercise,
    WorkspaceSession,
)
from apps.workspace.services import docker_env, git_ops, manifest, paths, reaper, scaffolder
from apps.workspace.services import submission as submission_service

logger = logging.getLogger(__name__)

#: Never walked when building the file tree; noise the user did not write.
TREE_SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".grading"}


def _owned_session(request: HttpRequest, pk: int) -> WorkspaceSession:
    """Fetch a session belonging to the requesting user, or 404."""
    return get_object_or_404(
        WorkspaceSession.objects.select_related("exercise", "user"), pk=pk, user=request.user
    )


def _enforce_deadline(session: WorkspaceSession) -> bool:
    """End a session whose deadline has passed, and queue it for grading.

    One of five enforcement points; the others are the heartbeat endpoint, the submit
    handler, the notes handler, and the reaper task. The client is never trusted for
    any of them.

    Returns:
        Whether the session was ended by this call.
    """
    if session.status != WorkspaceSession.Status.IN_PROGRESS or not session.is_time_up:
        return False

    WorkspaceEvent.log(session, WorkspaceEvent.Kind.TIMED_OUT)
    _enqueue_grading(session, WorkspaceSession.EndReason.TIMED_OUT)
    return True


def _enqueue_grading(session: WorkspaceSession, end_reason: str) -> bool:
    """Hand a session to the background grader, falling back to inline grading.

    Returns:
        Whether the work was dispatched to a worker. ``False`` means it was graded
        inline, which is slow but better than silently doing nothing when no worker
        is running.
    """
    from apps.workspace.tasks import grade_submission

    session.status = WorkspaceSession.Status.GRADING
    session.save(update_fields=["status"])
    try:
        grade_submission.delay(session.pk, end_reason)
        return True
    except Exception as exc:  # noqa: BLE001 - broker down, kombu raises broadly
        logger.warning("could not enqueue grading for %s, running inline: %s", session.pk, exc)
        submission_service.capture_and_grade(session, end_reason=end_reason)
        return False


# ---------------------------------------------------------------------------
# Catalog and exercise detail
# ---------------------------------------------------------------------------


class WorkspaceCatalogView(LoginRequiredMixin, ListView):
    """The exercise catalog, filterable by type, difficulty and database."""

    model = WorkspaceExercise
    template_name = "workspace/catalog.html"
    context_object_name = "exercises"

    def get_queryset(self):
        """Return active exercises, narrowed by the querystring filters.

        The database filter is applied in Python rather than as a
        ``databases__contains`` JSON lookup, because that lookup raises
        ``NotSupportedError`` on SQLite -- which is what dev falls back to. The
        catalog is at most a few dozen rows, so the cost is irrelevant and it works
        identically on every backend.
        """
        queryset = WorkspaceExercise.objects.filter(is_active=True)
        params = self.request.GET
        if exercise_type := params.get("type"):
            queryset = queryset.filter(exercise_type=exercise_type)
        if difficulty := params.get("difficulty"):
            queryset = queryset.filter(difficulty=difficulty)
        if database := params.get("database"):
            matching = [e.pk for e in queryset if database in (e.databases or [])]
            queryset = queryset.filter(pk__in=matching)
        return queryset

    def get_context_data(self, **kwargs) -> dict:
        """Add filter options, the active session banner, and grouping by type."""
        context = super().get_context_data(**kwargs)
        exercises = list(context["exercises"])

        by_type: dict[str, list] = {}
        for exercise in exercises:
            by_type.setdefault(exercise.get_exercise_type_display(), []).append(exercise)

        context["grouped"] = sorted(by_type.items())
        context["type_choices"] = WorkspaceExercise._meta.get_field("exercise_type").choices
        context["difficulty_choices"] = WorkspaceExercise._meta.get_field("difficulty").choices
        context["selected"] = {
            "type": self.request.GET.get("type", ""),
            "difficulty": self.request.GET.get("difficulty", ""),
            "database": self.request.GET.get("database", ""),
        }
        context["active_session"] = (
            WorkspaceSession.objects.filter(
                user=self.request.user, status__in=WorkspaceSession.ACTIVE_STATUSES
            )
            .select_related("exercise")
            .first()
        )
        context["total_count"] = WorkspaceExercise.objects.filter(is_active=True).count()
        return context


@login_required
@require_GET
def doctor_check(request: HttpRequest) -> HttpResponse:
    """Probe the local environment and render the result as an HTMX partial."""
    return render(request, "workspace/partials/_doctor.html", {"doctor": docker_env.doctor()})


class WorkspaceExerciseDetailView(LoginRequiredMixin, DetailView):
    """Shows the brief and exactly what will be created on disk."""

    model = WorkspaceExercise
    template_name = "workspace/exercise.html"
    context_object_name = "exercise"

    def get_context_data(self, **kwargs) -> dict:
        """Add the destination path, environment report, and any active session."""
        context = super().get_context_data(**kwargs)
        exercise = self.object
        context["workspace_path"] = paths.workspace_root() / paths.session_dir_name(
            exercise.exercise_number, exercise.slug
        )
        context["doctor"] = docker_env.doctor()
        context["active_session"] = WorkspaceSession.objects.filter(
            user=self.request.user, exercise=exercise, status__in=WorkspaceSession.ACTIVE_STATUSES
        ).first()
        return context


@login_required
@require_POST
def start_session(request: HttpRequest, slug: str) -> HttpResponse:
    """Create a session and scaffold its workspace.

    The clock does **not** start here. Scaffolding and container bring-up happen
    while the session is in ``READY``, so environment setup never eats into the time
    box.
    """
    exercise = get_object_or_404(WorkspaceExercise, slug=slug, is_active=True)

    existing = WorkspaceSession.objects.filter(
        user=request.user, exercise=exercise, status__in=WorkspaceSession.ACTIVE_STATUSES
    ).first()
    if existing:
        # Re-entry, not a collision: send them back to where they left off.
        return redirect(existing.get_absolute_url())

    report = docker_env.doctor()
    blockers = (
        report.blockers()
        if exercise.needs_docker
        else ([] if report.ready_without_docker else report.blockers())
    )
    if blockers:
        for blocker in blockers:
            messages.error(request, blocker)
        return redirect("workspace:exercise", slug=slug)

    try:
        with transaction.atomic():
            session = WorkspaceSession.objects.create(
                user=request.user,
                exercise=exercise,
                exercise_type=exercise.exercise_type,
                difficulty=exercise.difficulty,
                time_limit_seconds=exercise.time_limit_seconds,
                template_checksum=exercise.template_checksum,
                status=WorkspaceSession.Status.SCAFFOLDING,
            )
    except IntegrityError:
        # The uniqueness constraint fired: another tab won the race.
        session = WorkspaceSession.objects.filter(
            user=request.user, exercise=exercise, status__in=WorkspaceSession.ACTIVE_STATUSES
        ).first()
        return redirect(session.get_absolute_url() if session else "workspace:catalog")

    result = scaffolder.scaffold(session)
    if not result.ok:
        messages.error(
            request, _("Could not set up the workspace: %(error)s") % {"error": result.error}
        )
    return redirect("workspace:prepare", pk=session.pk)


# ---------------------------------------------------------------------------
# Prepare (off the clock)
# ---------------------------------------------------------------------------


#: Shown on the prepare page when a manifest cannot be read. Deliberately generic:
#: every base app brings its stack up this way, and anything beyond that is per-app.
FALLBACK_SETUP_COMMANDS = ["docker compose up -d --wait", "make test"]


def _manifest_setup_commands(base_app: str) -> list[str]:
    """Return the base app's authored setup steps for the prepare page.

    Read from the manifest rather than hardcoded, because the steps genuinely differ
    per app -- a Django app migrates and seeds, a warehouse app loads and rolls up,
    and a library app does neither. A hardcoded list is wrong for four of the five
    base apps and tells the user to run a make target that does not exist.

    Args:
        base_app: The template directory name.

    Returns:
        The manifest's ``setup_commands``, or a generic fallback if the manifest
        cannot be read. A broken manifest must not take the prepare page down -- the
        user can still run the commands from the README.
    """
    try:
        commands = manifest.load_manifest(base_app).setup_commands
    except WorkspaceError:
        logger.warning("could not read setup_commands for %s", base_app, exc_info=True)
        return list(FALLBACK_SETUP_COMMANDS)
    return list(commands) or list(FALLBACK_SETUP_COMMANDS)


class WorkspacePrepareView(LoginRequiredMixin, DetailView):
    """The off-the-clock setup page. Shows the path and container status, no timer."""

    template_name = "workspace/prepare.html"
    context_object_name = "session"

    def get_queryset(self):
        """Only the owner's not-yet-started sessions."""
        return WorkspaceSession.objects.select_related("exercise").filter(
            user=self.request.user,
            status__in=[
                WorkspaceSession.Status.SCAFFOLDING,
                WorkspaceSession.Status.READY,
                WorkspaceSession.Status.FAILED,
            ],
        )

    def get_context_data(self, **kwargs) -> dict:
        """Add setup commands, container state and the worker warning."""
        context = super().get_context_data(**kwargs)
        session = self.object
        report = docker_env.doctor()
        context["doctor"] = report
        context["containers"] = (
            docker_env.compose_ps(session.compose_project, Path(session.workspace_path))
            if session.compose_project and session.workspace_path
            else []
        )
        context["setup_commands"] = [
            f"cd {session.workspace_path}",
            *_manifest_setup_commands(session.exercise.base_app),
        ]
        context["ready"] = session.status == WorkspaceSession.Status.READY
        return context


@login_required
@require_POST
def start_containers(request: HttpRequest, pk: int) -> HttpResponse:
    """Bring the exercise's containers up. Called from the prepare page."""
    session = _owned_session(request, pk)
    ok, output = scaffolder.start_containers(session)
    if ok:
        messages.success(request, _("Containers are up and healthy."))
    else:
        messages.error(
            request, _("Containers did not start: %(output)s") % {"output": output[-400:]}
        )
    return redirect("workspace:prepare", pk=pk)


@login_required
@require_POST
def begin_session(request: HttpRequest, pk: int) -> HttpResponse:
    """Start the clock and move to the working page."""
    session = _owned_session(request, pk)
    if session.status != WorkspaceSession.Status.READY:
        messages.error(request, _("This exercise is not ready to start."))
        return redirect("workspace:prepare", pk=pk)

    session.begin()
    WorkspaceEvent.log(session, WorkspaceEvent.Kind.BEGUN)
    return redirect("workspace:session", pk=pk)


# ---------------------------------------------------------------------------
# The working session
# ---------------------------------------------------------------------------


@method_decorator(never_cache, name="dispatch")
class WorkspaceSessionView(LoginRequiredMixin, DetailView):
    """The working page: timer, brief, file tree, notes, submit.

    ``never_cache`` so the back button re-hits the server rather than showing a
    stale countdown.
    """

    template_name = "workspace/session.html"
    context_object_name = "session"

    def get_queryset(self):
        """Only the owner's in-progress sessions."""
        return WorkspaceSession.objects.select_related("exercise").filter(
            user=self.request.user, status=WorkspaceSession.Status.IN_PROGRESS
        )

    def get(self, request, *args, **kwargs):
        """Enforce the deadline before rendering."""
        self.object = self.get_object()
        if _enforce_deadline(self.object):
            return redirect("workspace:results", pk=self.object.pk)
        return self.render_to_response(self.get_context_data(object=self.object))

    def get_context_data(self, **kwargs) -> dict:
        """Add timer seed values, hints revealed so far, and the workspace path."""
        context = super().get_context_data(**kwargs)
        session = self.object
        exercise = session.exercise
        context["time_remaining"] = session.time_remaining_seconds
        context["available_hints"] = (exercise.hints or [])[: session.hints_used]
        context["has_more_hints"] = session.hints_used < len(exercise.hints or [])
        context["total_hints"] = len(exercise.hints or [])
        context["heartbeat_interval"] = settings.WORKSPACE_HEARTBEAT_INTERVAL_SECONDS
        return context


@login_required
@require_GET
def heartbeat(request: HttpRequest, pk: int) -> JsonResponse:
    """Report remaining time and workspace health.

    Merges the deadline, directory existence and container state into one poll, since
    all three are actionable and three separate polls would be wasteful.
    """
    session = _owned_session(request, pk)
    ended = _enforce_deadline(session)
    session.refresh_from_db()

    workspace = Path(session.workspace_path) if session.workspace_path else None
    workspace_ok = bool(workspace and workspace.is_dir())
    if not workspace_ok and session.status == WorkspaceSession.Status.IN_PROGRESS:
        WorkspaceEvent.log(session, WorkspaceEvent.Kind.WORKSPACE_MISSING)

    dirty = commits = 0
    if workspace_ok:
        try:
            dirty = len(git_ops.run_git(workspace, "status", "--porcelain").splitlines())
            commits = git_ops.commit_count(workspace, since=session.seed_commit_sha)
        except WorkspaceError:
            workspace_ok = False

    return JsonResponse(
        {
            "time_remaining": session.time_remaining_seconds,
            "time_limit": session.time_limit_seconds,
            "is_time_up": session.is_time_up,
            "status": session.status,
            "ended": ended,
            "workspace_ok": workspace_ok,
            "dirty_files": dirty,
            "commits": commits,
            "containers": (
                docker_env.compose_ps(session.compose_project, workspace)
                if workspace_ok and session.compose_project
                else []
            ),
            "results_url": session.get_results_url(),
        }
    )


@login_required
@require_GET
def file_tree(request: HttpRequest, pk: int) -> HttpResponse:
    """Render a read-only file tree of the workspace."""
    session = _owned_session(request, pk)
    root = Path(session.workspace_path) if session.workspace_path else None
    entries: list[dict] = []
    modified: set[str] = set()

    if root and root.is_dir():
        try:
            for line in git_ops.run_git(root, "status", "--porcelain").splitlines():
                modified.add(line[3:].strip())
        except WorkspaceError:
            pass

        limit = settings.WORKSPACE_TREE_MAX_ENTRIES
        for path in sorted(root.rglob("*")):
            if len(entries) >= limit:
                break
            if any(part in TREE_SKIP for part in path.relative_to(root).parts):
                continue
            if path.name == settings.WORKSPACE_SENTINEL_FILENAME:
                continue
            relative = path.relative_to(root).as_posix()
            entries.append(
                {
                    "path": relative,
                    "name": path.name,
                    "depth": len(path.relative_to(root).parts) - 1,
                    "is_dir": path.is_dir(),
                    "modified": relative in modified,
                }
            )

    return render(
        request,
        "workspace/partials/_file_tree.html",
        {"session": session, "entries": entries, "exists": bool(root and root.is_dir())},
    )


@login_required
@require_GET
def file_preview(request: HttpRequest, pk: int) -> HttpResponse:
    """Render one file, read-only.

    The requested path goes through the containment check in
    :func:`apps.workspace.services.paths.safe_join`; without it a crafted ``?path=``
    would read arbitrary files off disk through the user's own dev server.
    """
    session = _owned_session(request, pk)
    relative = request.GET.get("path", "")
    if not session.workspace_path:
        raise Http404("This session has no workspace.")

    try:
        target = paths.safe_join(Path(session.workspace_path), relative)
    except UnsafePathError as exc:
        logger.warning("rejected file preview for session %s: %s", pk, exc)
        return HttpResponse(_("Invalid path."), status=400)

    if not target.is_file():
        raise Http404("No such file.")

    limit = settings.WORKSPACE_FILE_PREVIEW_MAX_BYTES
    raw = target.read_bytes()[: limit + 1]
    truncated = len(raw) > limit
    binary = b"\x00" in raw[:2048]

    return render(
        request,
        "workspace/partials/_file_preview.html",
        {
            "path": relative,
            "content": "" if binary else raw[:limit].decode("utf-8", errors="replace"),
            "binary": binary,
            "truncated": truncated,
            "size": target.stat().st_size,
        },
    )


@login_required
@require_POST
def save_notes(request: HttpRequest, pk: int) -> HttpResponse:
    """Autosave the engineering notes."""
    session = _owned_session(request, pk)
    if session.status != WorkspaceSession.Status.IN_PROGRESS:
        return HttpResponse(_("This session is closed."), status=409)
    if _enforce_deadline(session):
        return HttpResponse(_("Time is up."), status=409)

    session.user_notes = request.POST.get("notes", "")
    session.save(update_fields=["user_notes"])
    return render(request, "workspace/partials/_notes_saved.html", {})


@login_required
@require_POST
def record_fairness(request: HttpRequest, pk: int) -> HttpResponse:
    """Record whether the engineer thought their grade was fair.

    This is the rubric's only source of human calibration data, so it is deliberately
    cheap to answer and re-answerable: an engineer who clicks "too harsh" and then reads
    the feedback and changes their mind should be able to say so, and the later answer is
    the better one.

    The grade itself is never altered. A fairness verdict is evidence about the rubric,
    not an appeal against one result -- letting it move the letter would make the
    evidence worthless.
    """
    session = get_object_or_404(WorkspaceSession, pk=pk, user=request.user)
    grade = getattr(session, "grade", None)
    if grade is None:
        return HttpResponse(_("This attempt has not been graded yet."), status=409)

    verdict = request.POST.get("fairness", "")
    if verdict not in GradeFairness.values:
        return HttpResponse(_("Unrecognised answer."), status=400)

    grade.fairness = verdict
    grade.fairness_note = (request.POST.get("note") or "")[:500]
    grade.fairness_recorded_at = timezone.now()
    grade.save(update_fields=["fairness", "fairness_note", "fairness_recorded_at"])

    WorkspaceEvent.log(session, WorkspaceEvent.Kind.FAIRNESS_RECORDED, fairness=verdict)
    logger.info(
        "fairness for session %s: %s (grade %s, rubric %s)",
        session.pk,
        verdict,
        grade.letter_grade,
        grade.rubric_version,
    )
    return render(
        request,
        "workspace/partials/_fairness.html",
        {
            "session": session,
            "grade": grade,
            "just_saved": True,
            "fairness_choices": GradeFairness.choices,
        },
    )


@login_required
@require_POST
def reveal_hint(request: HttpRequest, pk: int) -> HttpResponse:
    """Reveal the next hint, at a cost to the engineering score."""
    session = _owned_session(request, pk)
    hints = session.exercise.hints or []
    if session.status != WorkspaceSession.Status.IN_PROGRESS:
        return HttpResponse(_("This session is closed."), status=409)
    if session.hints_used >= len(hints):
        return HttpResponse(_("No more hints."), status=400)

    session.hints_used += 1
    session.save(update_fields=["hints_used"])
    WorkspaceEvent.log(session, WorkspaceEvent.Kind.HINT_REVEALED, index=session.hints_used)

    return render(
        request,
        "workspace/partials/_hint.html",
        {
            "hint": hints[session.hints_used - 1],
            "index": session.hints_used,
            "has_more": session.hints_used < len(hints),
        },
    )


# ---------------------------------------------------------------------------
# Submission and results
# ---------------------------------------------------------------------------


@login_required
@require_POST
def submit_work(request: HttpRequest, pk: int) -> HttpResponse:
    """Capture the work and queue it for grading."""
    session = _owned_session(request, pk)

    if session.status not in {
        WorkspaceSession.Status.IN_PROGRESS,
        WorkspaceSession.Status.READY,
    }:
        return redirect("workspace:results", pk=pk)

    if session.is_past_grace:
        # Past the grace window: the reaper owns this one now.
        messages.warning(
            request, _("The deadline passed, so your work was captured automatically.")
        )
        _enqueue_grading(session, WorkspaceSession.EndReason.TIMED_OUT)
        return redirect("workspace:results", pk=pk)

    reason = (
        WorkspaceSession.EndReason.TIMED_OUT
        if session.is_time_up
        else WorkspaceSession.EndReason.SUBMITTED
    )
    queued = _enqueue_grading(session, reason)
    if not queued:
        messages.info(
            request,
            _("No background worker is running, so grading ran inline and may have been slow."),
        )
    return redirect("workspace:results", pk=pk)


@login_required
@require_GET
def grade_status(request: HttpRequest, pk: int) -> JsonResponse:
    """Report grading progress, polled by the results page."""
    session = _owned_session(request, pk)
    return JsonResponse(submission_service.status_payload(session))


@login_required
@require_POST
def regrade(request: HttpRequest, pk: int) -> HttpResponse:
    """Re-grade a stored submission without re-reading the workspace.

    The captured bytes are what get graded, so a retry an hour later still grades
    exactly what was submitted.
    """
    session = _owned_session(request, pk)
    if not hasattr(session, "submission"):
        messages.error(request, _("There is nothing captured to re-grade."))
        return redirect("workspace:results", pk=pk)

    try:
        submission_service.grade(session, session.submission)
        messages.success(request, _("Re-graded."))
    except WorkspaceError as exc:
        messages.error(request, str(exc))
    except Exception as exc:  # noqa: BLE001 - surfaced to the user
        logger.exception("regrade failed for session %s", pk)
        messages.error(request, _("Could not re-grade: %(error)s") % {"error": exc})
    return redirect("workspace:results", pk=pk)


@login_required
@require_POST
def abandon_session(request: HttpRequest, pk: int) -> HttpResponse:
    """Abandon an attempt and tear its workspace down."""
    session = _owned_session(request, pk)
    reaper.teardown(session, reason=WorkspaceSession.EndReason.ABANDONED)
    messages.info(request, _("Exercise abandoned. Your workspace was archived, not deleted."))
    return redirect("workspace:catalog")


@login_required
@require_POST
def teardown_workspace(request: HttpRequest, pk: int) -> HttpResponse:
    """Stop containers and archive the workspace, after grading."""
    session = _owned_session(request, pk)
    outcome = reaper.teardown(session)
    if outcome["archived"]:
        messages.success(request, _("Workspace archived and containers stopped."))
    else:
        messages.info(request, _("Nothing left to tear down."))
    return redirect("workspace:results", pk=pk)


class WorkspaceResultsView(LoginRequiredMixin, DetailView):
    """The grade, the checks, and what a senior would have done."""

    template_name = "workspace/results.html"
    context_object_name = "session"

    def get_queryset(self):
        """The owner's sessions that have reached grading or beyond."""
        return WorkspaceSession.objects.select_related("exercise").filter(
            user=self.request.user,
            status__in=[
                WorkspaceSession.Status.GRADING,
                WorkspaceSession.Status.COMPLETED,
                WorkspaceSession.Status.TIMED_OUT,
                WorkspaceSession.Status.ABANDONED,
            ],
        )

    def get_context_data(self, **kwargs) -> dict:
        """Add the grade, check rows and cap explanations."""
        from apps.workspace.grading import GATE_EXPLANATIONS

        context = super().get_context_data(**kwargs)
        session = self.object
        grade = getattr(session, "grade", None)
        submission = getattr(session, "submission", None)

        context["grade"] = grade
        context["submission"] = submission
        context["checks"] = (
            submission.check_results.all().order_by("-required", "check_id") if submission else []
        )
        context["cap_explanations"] = (
            [GATE_EXPLANATIONS.get(code, code) for code in grade.applied_caps] if grade else []
        )
        context["pending"] = grade is None
        context["fairness_choices"] = GradeFairness.choices
        context["workspace_exists"] = bool(
            session.workspace_path and Path(session.workspace_path).is_dir()
        )
        return context


class WorkspaceHistoryView(LoginRequiredMixin, ListView):
    """This mode's own stats page.

    Deliberately separate from the subject dashboards: one exercise spans several
    technologies, so attributing it to a single subject would misreport both.
    """

    template_name = "workspace/history.html"
    context_object_name = "sessions"
    paginate_by = 25

    def get_queryset(self):
        """The owner's finished attempts, newest first."""
        return (
            WorkspaceSession.objects.select_related("exercise", "grade")
            .filter(user=self.request.user)
            .exclude(status=WorkspaceSession.Status.SCAFFOLDING)
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs) -> dict:
        """Add aggregate grade-point statistics."""
        context = super().get_context_data(**kwargs)
        graded = [
            session.grade
            for session in context["sessions"]
            if getattr(session, "grade", None) is not None
        ]
        context["graded_count"] = len(graded)
        context["average_points"] = (
            round(sum(float(g.grade_points) for g in graded) / len(graded), 2) if graded else None
        )
        context["average_score"] = (
            round(sum(g.overall_score for g in graded) / len(graded)) if graded else None
        )
        return context
