"""URL configuration for the coding app."""

from django.urls import path

from . import views

app_name = "coding"

urlpatterns = [
    # Configuration
    path(
        "<slug:subject_slug>/",
        views.CodingConfigView.as_view(),
        name="config",
    ),
    # Start session
    path(
        "<slug:subject_slug>/start/",
        views.start_coding_session,
        name="start",
    ),
    # Challenge view (Monaco editor)
    path(
        "<slug:subject_slug>/session/<int:pk>/",
        views.CodingChallengeView.as_view(),
        name="challenge",
    ),
    # Save draft (HTMX endpoint)
    path(
        "<slug:subject_slug>/session/<int:pk>/save-draft/",
        views.save_draft,
        name="save_draft",
    ),
    # Reveal hint (HTMX endpoint)
    path(
        "<slug:subject_slug>/session/<int:pk>/hint/",
        views.reveal_hint,
        name="reveal_hint",
    ),
    # Submit for evaluation
    path(
        "<slug:subject_slug>/session/<int:pk>/submit/",
        views.submit_code,
        name="submit",
    ),
    # Abandon session
    path(
        "<slug:subject_slug>/session/<int:pk>/abandon/",
        views.abandon_session,
        name="abandon",
    ),
    # Results view
    path(
        "<slug:subject_slug>/session/<int:pk>/results/",
        views.CodingResultsView.as_view(),
        name="results",
    ),
]
