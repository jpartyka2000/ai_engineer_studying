"""URL configuration for the visuals app."""

from django.urls import path

from . import views

app_name = "visuals"

urlpatterns = [
    # Topic list: show available visual topics for a subject
    path(
        "<slug:subject_slug>/",
        views.VisualTopicListView.as_view(),
        name="topic_list",
    ),
    # Visual viewer: main step-by-step viewer
    path(
        "<slug:subject_slug>/<slug:topic_slug>/",
        views.VisualViewerView.as_view(),
        name="viewer",
    ),
    # Update progress (POST, called when user views a step)
    path(
        "<slug:subject_slug>/<slug:topic_slug>/progress/",
        views.update_progress,
        name="update_progress",
    ),
    # Request explanation (POST, returns stream URL)
    path(
        "<slug:subject_slug>/<slug:topic_slug>/explain/<int:step_number>/",
        views.explain_step,
        name="explain_step",
    ),
    # Stream explanation (SSE)
    path(
        "<slug:subject_slug>/<slug:topic_slug>/explain/<int:step_number>/stream/",
        views.stream_explanation,
        name="stream_explanation",
    ),
]
