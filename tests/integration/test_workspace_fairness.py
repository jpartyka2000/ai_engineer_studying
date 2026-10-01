"""Tests for the fairness control on the results page.

This endpoint is the rubric's only source of human calibration data, so two properties
matter more than the happy path: it must never alter the grade it is asking about, and it
must reject anything it did not offer. A fairness verdict that could move a letter would
be an appeal rather than evidence, and the evidence would be worthless.
"""

import pytest
from django.urls import reverse

from apps.workspace.enums import GradeFairness
from apps.workspace.models import (
    WorkspaceEvent,
    WorkspaceExercise,
    WorkspaceGrade,
    WorkspaceSession,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="engineer", password="pw")


@pytest.fixture
def other_user(django_user_model):
    return django_user_model.objects.create_user(username="someone-else", password="pw")


@pytest.fixture
def exercise(db):
    from django.core.management import call_command

    call_command("seed_workspace_exercises", slug="ex-001-invoice-drops-final-day", verbosity=0)
    return WorkspaceExercise.objects.get(slug="ex-001-invoice-drops-final-day")


@pytest.fixture
def graded_session(user, exercise):
    session = WorkspaceSession.objects.create(
        user=user,
        exercise=exercise,
        exercise_type=exercise.exercise_type,
        difficulty=exercise.difficulty,
        time_limit_seconds=exercise.time_limit_seconds,
        status=WorkspaceSession.Status.COMPLETED,
    )
    WorkspaceGrade.objects.create(
        session=session,
        overall_score=79,
        base_score=79,
        letter_grade="C+",
        uncapped_letter="C+",
        dimension_scores={"correctness": 92, "engineering": 88, "documentation": 12},
        rubric_version="2026.03-3",
    )
    return session


def post(client, session, **data):
    return client.post(reverse("workspace:fairness", kwargs={"pk": session.pk}), data)


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


def test_a_verdict_is_recorded_with_its_note_and_timestamp(client, user, graded_session):
    client.force_login(user)
    response = post(client, graded_session, fairness="too_harsh", note="documentation too heavy")

    assert response.status_code == 200
    grade = WorkspaceGrade.objects.get(session=graded_session)
    assert grade.fairness == GradeFairness.TOO_HARSH
    assert grade.fairness_note == "documentation too heavy"
    assert grade.fairness_recorded_at is not None


def test_recording_a_verdict_never_changes_the_grade(client, user, graded_session):
    """The decisive property. Evidence about the rubric, not an appeal against a result."""
    before = WorkspaceGrade.objects.get(session=graded_session)
    fields = (before.overall_score, before.letter_grade, before.grade_points, before.base_score)

    client.force_login(user)
    post(client, graded_session, fairness="too_harsh", note="unfair")

    after = WorkspaceGrade.objects.get(session=graded_session)
    assert (after.overall_score, after.letter_grade, after.grade_points, after.base_score) == fields
    assert after.dimension_scores == before.dimension_scores


def test_a_verdict_can_be_changed(client, user, graded_session):
    """Someone who reads the feedback and reconsiders should be able to say so, and the
    later answer is the better one."""
    client.force_login(user)
    post(client, graded_session, fairness="too_harsh")
    post(client, graded_session, fairness="about_right", note="fair after reading it")

    grade = WorkspaceGrade.objects.get(session=graded_session)
    assert grade.fairness == GradeFairness.ABOUT_RIGHT
    assert grade.fairness_note == "fair after reading it"


def test_a_verdict_is_logged_under_its_own_event_kind(client, user, graded_session):
    """Not under GRADED, which `submission.py` writes when grading finishes.

    Reusing that kind would put a second "Graded" event on the timeline, carrying a
    fairness payload, every time someone answered -- and again each time they changed
    their answer. The session history is the record of what happened to an attempt; a
    verdict about a grade is not the attempt being graded.
    """
    client.force_login(user)
    post(client, graded_session, fairness="too_harsh")

    kinds = list(graded_session.events.values_list("kind", flat=True))
    assert kinds == [WorkspaceEvent.Kind.FAIRNESS_RECORDED]


def test_a_long_note_is_truncated_rather_than_rejected(client, user, graded_session):
    client.force_login(user)
    post(client, graded_session, fairness="about_right", note="x" * 900)
    assert len(WorkspaceGrade.objects.get(session=graded_session).fairness_note) == 500


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("verdict", ["", "unfair", "A+", "too_harsh ", "TOO_HARSH"])
def test_an_answer_that_was_not_offered_is_rejected(client, user, graded_session, verdict):
    client.force_login(user)
    assert post(client, graded_session, fairness=verdict).status_code == 400
    assert WorkspaceGrade.objects.get(session=graded_session).fairness == ""


def test_an_ungraded_attempt_cannot_be_judged(client, user, exercise):
    session = WorkspaceSession.objects.create(
        user=user,
        exercise=exercise,
        exercise_type=exercise.exercise_type,
        difficulty=exercise.difficulty,
        time_limit_seconds=exercise.time_limit_seconds,
        status=WorkspaceSession.Status.GRADING,
    )
    client.force_login(user)
    assert post(client, session, fairness="about_right").status_code == 409


def test_another_users_grade_cannot_be_judged(client, other_user, graded_session):
    client.force_login(other_user)
    assert post(client, graded_session, fairness="too_harsh").status_code == 404
    assert WorkspaceGrade.objects.get(session=graded_session).fairness == ""


def test_anonymous_requests_are_redirected_to_login(client, graded_session):
    response = post(client, graded_session, fairness="too_harsh")
    assert response.status_code == 302
    assert WorkspaceGrade.objects.get(session=graded_session).fairness == ""


def test_get_is_not_allowed(client, user, graded_session):
    client.force_login(user)
    url = reverse("workspace:fairness", kwargs={"pk": graded_session.pk})
    assert client.get(url).status_code == 405


# ---------------------------------------------------------------------------
# The results page
# ---------------------------------------------------------------------------


def test_the_results_page_offers_every_choice(client, user, graded_session):
    client.force_login(user)
    html = client.get(
        reverse("workspace:results", kwargs={"pk": graded_session.pk})
    ).content.decode()

    assert "Was this grade fair?" in html
    for value, label in GradeFairness.choices:
        assert value in html
        assert str(label) in html


def test_the_results_page_shows_a_previously_recorded_verdict(client, user, graded_session):
    client.force_login(user)
    post(client, graded_session, fairness="too_harsh", note="documentation too heavy")

    html = client.get(
        reverse("workspace:results", kwargs={"pk": graded_session.pk})
    ).content.decode()
    assert "Too harsh" in html
    assert "documentation too heavy" in html
    assert "2026.03-3" in html


def test_the_control_carries_the_htmx_wiring_it_needs(client, user, graded_session):
    """Guards the part a Django-level POST cannot reach.

    The tests above post directly, so they would pass even if the browser could never
    produce that request. Each button therefore has to carry its own hx-post and hx-vals
    rather than relying on htmx forwarding a form submitter's name/value, the note field
    has to be pulled in explicitly, and a CSRF token has to exist on the page for
    main.js to copy into the X-CSRFToken header.
    """
    client.force_login(user)
    html = client.get(
        reverse("workspace:results", kwargs={"pk": graded_session.pk})
    ).content.decode()

    url = reverse("workspace:fairness", kwargs={"pk": graded_session.pk})
    assert html.count(f'hx-post="{url}"') == len(GradeFairness.choices)
    for value, _label in GradeFairness.choices:
        assert f'hx-vals=\'{{"fairness": "{value}"}}\'' in html
    assert 'hx-include="#ws-fairness-note"' in html
    assert 'id="ws-fairness-note"' in html
    assert 'hx-target="#ws-fairness"' in html
    assert 'hx-swap="outerHTML"' in html
    assert "csrfmiddlewaretoken" in html
