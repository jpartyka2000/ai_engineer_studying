"""URL configuration for the equations app."""

from django.urls import path

from . import views

app_name = "equations"

urlpatterns = [
    path(
        "<slug:subject_slug>/",
        views.MathConfigView.as_view(),
        name="config",
    ),
    path(
        "<slug:subject_slug>/start/",
        views.start_math_session,
        name="start",
    ),
    path(
        "<slug:subject_slug>/<int:pk>/",
        views.MathProblemView.as_view(),
        name="problem",
    ),
    path(
        "<slug:subject_slug>/<int:pk>/submit/",
        views.submit_answer,
        name="submit",
    ),
    path(
        "<slug:subject_slug>/<int:pk>/hint/",
        views.reveal_hint,
        name="hint",
    ),
    path(
        "<slug:subject_slug>/<int:pk>/skip/",
        views.skip_problem,
        name="skip",
    ),
    path(
        "<slug:subject_slug>/<int:pk>/abandon/",
        views.abandon_session,
        name="abandon",
    ),
    path(
        "<slug:subject_slug>/<int:pk>/results/",
        views.MathResultsView.as_view(),
        name="results",
    ),
]
