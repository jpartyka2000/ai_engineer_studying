"""URL configuration for the argument app."""

from django.urls import path

from . import views

app_name = "argument"

urlpatterns = [
    # Config page - select difficulty and heat level
    path(
        "<slug:subject_slug>/",
        views.ArgumentConfigView.as_view(),
        name="config",
    ),
    # Start new argument session (POST)
    path(
        "<slug:subject_slug>/start/",
        views.start_argument,
        name="start",
    ),
    # Active argument session (chat interface)
    path(
        "<slug:subject_slug>/<int:pk>/",
        views.ArgumentSessionView.as_view(),
        name="session",
    ),
    # Submit user response (POST, returns stream URL)
    path(
        "<slug:subject_slug>/<int:pk>/respond/",
        views.submit_response,
        name="respond",
    ),
    # Stream opponent response (SSE)
    path(
        "<slug:subject_slug>/<int:pk>/stream/<int:message_id>/",
        views.stream_response,
        name="stream",
    ),
    # End argument and get analysis (POST)
    path(
        "<slug:subject_slug>/<int:pk>/end/",
        views.end_argument,
        name="end",
    ),
    # Results page with analysis
    path(
        "<slug:subject_slug>/<int:pk>/results/",
        views.ArgumentResultsView.as_view(),
        name="results",
    ),
]
