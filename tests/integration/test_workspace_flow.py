"""End-to-end flow through the workspace views.

Walks the path a user actually takes -- catalog, exercise, start, prepare, begin,
heartbeat, submit, results -- with the Claude call mocked. The scaffolder runs for
real against the checked-in template, so this also exercises git history seeding.

The container-dependent parts (``docker compose up``, running the exercise's suite
inside the app container) are not exercised here; those need a built image and are
covered by running the exercise by hand.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time

from apps.workspace.models import WorkspaceEvent, WorkspaceExercise, WorkspaceSession
from apps.workspace.services import git_ops

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def workspace_root(tmp_path, settings):
    """Point scaffolding at a temp directory, never the developer's real one."""
    root = tmp_path / "home" / "user" / "workspaces"
    root.mkdir(parents=True)
    settings.WORKSPACE_ROOT = root
    return root


@pytest.fixture
def exercise(db):
    """Load the real authored catalog entry."""
    from django.core.management import call_command

    call_command("seed_workspace_exercises", slug="ex-001-invoice-drops-final-day", verbosity=0)
    return WorkspaceExercise.objects.get(slug="ex-001-invoice-drops-final-day")


@pytest.fixture
def logged_in(user) -> Client:
    client = Client(headers={"host": "localhost"})
    client.force_login(user)
    return client


@pytest.fixture
def no_docker_needed(exercise):
    """Let the flow run without Docker, which the harness cannot rely on."""
    exercise.needs_docker = False
    exercise.save(update_fields=["needs_docker"])
    return exercise


# ---------------------------------------------------------------------------
# Catalog and exercise detail
# ---------------------------------------------------------------------------


def test_catalog_lists_the_exercise(logged_in, exercise):
    response = logged_in.get(reverse("workspace:catalog"))
    assert response.status_code == 200
    # A substring with no characters Django would HTML-escape; the full title
    # contains an apostrophe, which renders as &#x27;.
    assert b"March invoices are short" in response.content


def test_catalog_requires_login(client):
    response = client.get(reverse("workspace:catalog"))
    assert response.status_code == 302


def test_catalog_filters_by_type(logged_in, exercise):
    response = logged_in.get(reverse("workspace:catalog"), {"type": "latency"})
    assert b"March invoices are short" not in response.content


def test_catalog_filters_by_difficulty(logged_in, exercise):
    hit = logged_in.get(reverse("workspace:catalog"), {"difficulty": "intermediate"})
    miss = logged_in.get(reverse("workspace:catalog"), {"difficulty": "beginner"})
    assert b"March invoices are short" in hit.content
    assert b"March invoices are short" not in miss.content


def test_catalog_filters_by_database(logged_in, exercise):
    """Regression test: a JSON `contains` lookup raises on SQLite.

    dev falls back to SQLite, so filtering with `databases__contains` made this
    query 500 rather than returning results.
    """
    hit = logged_in.get(reverse("workspace:catalog"), {"database": "postgres"})
    miss = logged_in.get(reverse("workspace:catalog"), {"database": "mongodb"})
    assert hit.status_code == 200
    assert miss.status_code == 200
    assert b"March invoices are short" in hit.content
    assert b"March invoices are short" not in miss.content


def test_catalog_filters_combine(logged_in, exercise):
    response = logged_in.get(
        reverse("workspace:catalog"),
        {"type": "critical_bug", "difficulty": "intermediate", "database": "postgres"},
    )
    assert response.status_code == 200
    assert b"March invoices are short" in response.content


def test_exercise_page_shows_the_destination_path(logged_in, exercise):
    response = logged_in.get(reverse("workspace:exercise", kwargs={"slug": exercise.slug}))
    assert response.status_code == 200
    assert b"ex-001-invoice-drops-final-day" in response.content


def test_exercise_page_does_not_leak_the_grading_notes(logged_in, exercise):
    """grading_notes names the root cause; it must never reach the browser."""
    response = logged_in.get(reverse("workspace:exercise", kwargs={"slug": exercise.slug}))
    assert b"_collect_base_tables" not in response.content
    assert b"__date__gte" not in response.content


def test_doctor_endpoint_renders(logged_in, exercise):
    response = logged_in.get(reverse("workspace:doctor"))
    assert response.status_code == 200
    assert b"git" in response.content


# ---------------------------------------------------------------------------
# Start and prepare
# ---------------------------------------------------------------------------


def test_start_scaffolds_and_lands_on_prepare(logged_in, no_docker_needed):
    response = logged_in.post(
        reverse("workspace:start", kwargs={"slug": no_docker_needed.slug}), follow=True
    )
    assert response.status_code == 200

    session = WorkspaceSession.objects.get()
    assert session.status == WorkspaceSession.Status.READY
    assert session.seed_commit_sha
    # The clock must NOT have started.
    assert session.started_at is None
    assert session.expires_at is None


def test_prepare_page_has_no_timer(logged_in, no_docker_needed):
    logged_in.post(reverse("workspace:start", kwargs={"slug": no_docker_needed.slug}))
    session = WorkspaceSession.objects.get()

    response = logged_in.get(reverse("workspace:prepare", kwargs={"pk": session.pk}))
    assert response.status_code == 200
    assert b'id="ws-timer"' not in response.content
    assert b"Start the clock" in response.content


def test_starting_twice_returns_the_same_session(logged_in, no_docker_needed):
    logged_in.post(reverse("workspace:start", kwargs={"slug": no_docker_needed.slug}))
    logged_in.post(reverse("workspace:start", kwargs={"slug": no_docker_needed.slug}))
    assert WorkspaceSession.objects.count() == 1


def test_scaffolded_repo_has_real_history_and_is_clean(logged_in, no_docker_needed):
    """History must match the manifest exactly, and the tree must start clean.

    The expected commit count is read from the manifest rather than hardcoded, so
    growing the base app does not break this test for the wrong reason.
    """
    from apps.workspace.services import manifest

    logged_in.post(reverse("workspace:start", kwargs={"slug": no_docker_needed.slug}))
    session = WorkspaceSession.objects.get()

    expected = len(manifest.load_manifest(no_docker_needed.base_app).seed_commits)
    log = git_ops.run_git(session.workspace_path, "log", "--oneline")
    assert len(log.splitlines()) == expected
    assert expected >= 5, "history should be long enough for git log and bisect to help"
    assert git_ops.is_tree_clean(session.workspace_path)


def test_the_defect_is_not_visible_as_a_change(logged_in, no_docker_needed):
    """git diff against the seed tag must be empty, or git log gives the answer away."""
    logged_in.post(reverse("workspace:start", kwargs={"slug": no_docker_needed.slug}))
    session = WorkspaceSession.objects.get()
    assert git_ops.run_git(session.workspace_path, "diff", "_seed") == ""


def test_solution_material_is_never_scaffolded(logged_in, no_docker_needed):
    from pathlib import Path

    logged_in.post(reverse("workspace:start", kwargs={"slug": no_docker_needed.slug}))
    session = WorkspaceSession.objects.get()
    assert not (Path(session.workspace_path) / "solution").exists()


# ---------------------------------------------------------------------------
# Begin and the working page
# ---------------------------------------------------------------------------


@pytest.fixture
def started(logged_in, no_docker_needed):
    """A session with the clock running."""
    logged_in.post(reverse("workspace:start", kwargs={"slug": no_docker_needed.slug}))
    session = WorkspaceSession.objects.get()
    logged_in.post(reverse("workspace:begin", kwargs={"pk": session.pk}))
    session.refresh_from_db()
    return session


def test_begin_starts_the_clock(started):
    assert started.status == WorkspaceSession.Status.IN_PROGRESS
    assert started.started_at is not None
    assert started.expires_at == started.started_at + timedelta(minutes=30)


def test_session_page_shows_the_timer_and_the_brief(logged_in, started):
    response = logged_in.get(reverse("workspace:session", kwargs={"pk": started.pk}))
    assert response.status_code == 200
    assert b'id="ws-timer"' in response.content
    assert b"INC-2291" in response.content
    # The CSRF token must be present or HTMX requests will be rejected.
    assert b"csrfmiddlewaretoken" in response.content


def test_session_page_does_not_leak_the_grading_notes(logged_in, started):
    response = logged_in.get(reverse("workspace:session", kwargs={"pk": started.pk}))
    assert b"symptom patch" not in response.content.lower()


def test_reloading_does_not_reset_the_clock(logged_in, started):
    """The bug in apps/coding, regression-tested here."""
    with freeze_time(timezone.now() + timedelta(minutes=12)):
        response = logged_in.get(reverse("workspace:session", kwargs={"pk": started.pk}))
        assert response.context["time_remaining"] == pytest.approx(18 * 60, abs=2)


def test_heartbeat_reports_time_and_workspace_health(logged_in, started):
    response = logged_in.get(reverse("workspace:heartbeat", kwargs={"pk": started.pk}))
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["workspace_ok"] is True
    assert body["is_time_up"] is False
    assert 0 < body["time_remaining"] <= 1800


def test_heartbeat_detects_a_deleted_workspace(logged_in, started):
    import shutil

    shutil.rmtree(started.workspace_path)
    body = logged_in.get(reverse("workspace:heartbeat", kwargs={"pk": started.pk})).json()
    assert body["workspace_ok"] is False
    assert started.events.filter(kind=WorkspaceEvent.Kind.WORKSPACE_MISSING).exists()


def test_notes_autosave(logged_in, started):
    response = logged_in.post(
        reverse("workspace:save_notes", kwargs={"pk": started.pk}),
        {"notes": "## Root cause\nDate coercion."},
    )
    assert response.status_code == 200
    started.refresh_from_db()
    assert "Date coercion" in started.user_notes


def test_hints_are_revealed_one_at_a_time(logged_in, started):
    response = logged_in.post(reverse("workspace:hint", kwargs={"pk": started.pk}))
    assert response.status_code == 200
    started.refresh_from_db()
    assert started.hints_used == 1


def test_hints_run_out(logged_in, started):
    total = len(started.exercise.hints)
    for _ in range(total):
        logged_in.post(reverse("workspace:hint", kwargs={"pk": started.pk}))
    assert logged_in.post(reverse("workspace:hint", kwargs={"pk": started.pk})).status_code == 400


# ---------------------------------------------------------------------------
# The file browser's path guard
# ---------------------------------------------------------------------------


def test_file_preview_renders_a_real_file(logged_in, started):
    response = logged_in.get(
        reverse("workspace:file", kwargs={"pk": started.pk}), {"path": "billing/services.py"}
    )
    assert response.status_code == 200
    assert b"line_items_for_period" in response.content


@pytest.mark.parametrize(
    "path",
    ["../../../../etc/passwd", "/etc/passwd", "billing/../../../../etc/passwd"],
)
def test_file_preview_rejects_traversal(logged_in, started, path):
    """The attack the containment check exists to stop."""
    response = logged_in.get(reverse("workspace:file", kwargs={"pk": started.pk}), {"path": path})
    assert response.status_code == 400
    assert b"root:" not in response.content


def test_file_tree_lists_files_and_hides_the_sentinel(logged_in, started):
    response = logged_in.get(reverse("workspace:tree", kwargs={"pk": started.pk}))
    assert response.status_code == 200
    assert b"services.py" in response.content
    assert b".ai-prep-workspace" not in response.content


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------


def test_another_user_cannot_reach_your_session(started, admin_user):
    other = Client(headers={"host": "localhost"})
    other.force_login(admin_user)
    assert other.get(reverse("workspace:session", kwargs={"pk": started.pk})).status_code == 404
    assert other.get(reverse("workspace:heartbeat", kwargs={"pk": started.pk})).status_code == 404


# ---------------------------------------------------------------------------
# Deadline enforcement
# ---------------------------------------------------------------------------


def test_visiting_after_the_deadline_ends_the_session(logged_in, started):
    started.expires_at = timezone.now() - timedelta(seconds=1)
    started.save(update_fields=["expires_at"])

    with patch("apps.workspace.services.submission.capture_and_grade") as graded:
        response = logged_in.get(
            reverse("workspace:session", kwargs={"pk": started.pk}), follow=True
        )

    assert response.status_code == 200
    started.refresh_from_db()
    assert started.status in {
        WorkspaceSession.Status.GRADING,
        WorkspaceSession.Status.TIMED_OUT,
    }
    assert graded.called or started.status == WorkspaceSession.Status.GRADING


def test_heartbeat_ends_an_expired_session(logged_in, started):
    started.expires_at = timezone.now() - timedelta(seconds=1)
    started.save(update_fields=["expires_at"])

    with patch("apps.workspace.services.submission.capture_and_grade"):
        body = logged_in.get(reverse("workspace:heartbeat", kwargs={"pk": started.pk})).json()

    assert body["is_time_up"] is True
    assert body["status"] != "in_progress"


def test_notes_are_rejected_after_the_deadline(logged_in, started):
    started.expires_at = timezone.now() - timedelta(seconds=1)
    started.save(update_fields=["expires_at"])

    with patch("apps.workspace.services.submission.capture_and_grade"):
        response = logged_in.post(
            reverse("workspace:save_notes", kwargs={"pk": started.pk}), {"notes": "late"}
        )
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------


def test_submitting_captures_the_work_and_redirects(logged_in, started):
    from pathlib import Path

    target = Path(started.workspace_path) / "billing" / "services.py"
    target.write_text(target.read_text().replace("created_at__lt=", "created_at__date__lte="))
    (Path(started.workspace_path) / "NOTES.md").write_text("## Root cause\nDate coercion.\n")

    # Pinned to the inline branch, because this test is about capture rather than about
    # dispatch. Left unpinned it inherits whatever the developer's Redis is doing: with a
    # broker reachable the work is queued, nothing consumes it, and there is no
    # submission to assert on. Which branch runs does not affect what is being tested --
    # the task and the fallback both call the same capture_and_grade.
    with (
        patch(
            "apps.workspace.tasks.grade_submission.delay",
            side_effect=OSError("Connection refused"),
        ),
        patch("apps.workspace.services.submission.grade") as graded,
    ):
        response = logged_in.post(
            reverse("workspace:submit", kwargs={"pk": started.pk}), follow=True
        )

    assert response.status_code == 200
    started.refresh_from_db()
    assert hasattr(started, "submission")
    assert started.submission.files_changed >= 1
    assert graded.called


def test_submitting_does_not_disturb_the_users_git_state(logged_in, started):
    from pathlib import Path

    workspace = Path(started.workspace_path)
    (workspace / "scratch.py").write_text("# thinking\n")
    before = git_ops.run_git(workspace, "status", "--porcelain")

    # Pinned to the inline branch so the capture this test is checking actually happens.
    # Unpinned and with a broker reachable, nothing is captured at all and the assertion
    # below is trivially true -- the test passes while testing nothing, which is a worse
    # failure than going red.
    with (
        patch(
            "apps.workspace.tasks.grade_submission.delay",
            side_effect=OSError("Connection refused"),
        ),
        patch("apps.workspace.services.submission.grade"),
    ):
        logged_in.post(reverse("workspace:submit", kwargs={"pk": started.pk}))

    assert git_ops.run_git(workspace, "status", "--porcelain") == before


def test_results_page_polls_while_grading(logged_in, started):
    # Pinned to the worker-present branch, the opposite of the two tests above: the
    # state being asserted is "queued, not yet graded", which only exists while
    # something else holds the work. Graded inline, the session would already be
    # COMPLETED by the time the response came back and there would be nothing to poll.
    with patch("apps.workspace.tasks.grade_submission.delay"):
        logged_in.post(reverse("workspace:submit", kwargs={"pk": started.pk}))

    response = logged_in.get(reverse("workspace:results", kwargs={"pk": started.pk}))
    assert response.status_code == 200
    assert b"Grading your work" in response.content


def test_grade_status_reports_grading_while_a_worker_has_it(logged_in, started):
    """With a worker available the request returns immediately, still grading."""
    with patch("apps.workspace.tasks.grade_submission.delay") as queued:
        logged_in.post(reverse("workspace:submit", kwargs={"pk": started.pk}))

    assert queued.called
    body = logged_in.get(reverse("workspace:grade_status", kwargs={"pk": started.pk})).json()
    assert body["graded"] is False
    assert body["status"] == "grading"


def test_submitting_falls_back_to_inline_when_the_broker_is_down(logged_in, started):
    """No worker must not mean no grade.

    With Redis unreachable, `.delay()` raises and the view grades inline instead --
    slower, but the alternative is a submission that silently goes nowhere.
    """
    with (
        patch(
            "apps.workspace.tasks.grade_submission.delay",
            side_effect=OSError("Connection refused"),
        ),
        patch("apps.workspace.services.submission.grade") as graded,
    ):
        logged_in.post(reverse("workspace:submit", kwargs={"pk": started.pk}))

    assert graded.called
    started.refresh_from_db()
    assert started.status == WorkspaceSession.Status.COMPLETED


# ---------------------------------------------------------------------------
# Abandon
# ---------------------------------------------------------------------------


def test_abandoning_archives_rather_than_deletes(logged_in, started):
    from pathlib import Path

    from apps.workspace.services import paths

    original = Path(started.workspace_path)
    logged_in.post(reverse("workspace:abandon", kwargs={"pk": started.pk}))

    started.refresh_from_db()
    assert started.status == WorkspaceSession.Status.ABANDONED
    assert not original.exists()
    assert any(paths.archive_root().iterdir())
