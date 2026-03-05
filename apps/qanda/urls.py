"""URL configuration for the qanda app."""

from django.urls import path

from . import views

app_name = "qanda"

urlpatterns = [
    # Home: list existing sessions or start new one
    path(
        "<slug:subject_slug>/",
        views.QAHomeView.as_view(),
        name="home",
    ),
    # Start new session (POST)
    path(
        "<slug:subject_slug>/start/",
        views.start_qa_session,
        name="start",
    ),
    # Active session (chat interface)
    path(
        "<slug:subject_slug>/<int:pk>/",
        views.QASessionView.as_view(),
        name="session",
    ),
    # Ask question (POST, returns message_id and stream URL)
    path(
        "<slug:subject_slug>/<int:pk>/ask/",
        views.ask_question,
        name="ask",
    ),
    # Stream response (SSE)
    path(
        "<slug:subject_slug>/<int:pk>/stream/<int:message_id>/",
        views.stream_response,
        name="stream",
    ),
    # Export conversation as markdown
    path(
        "<slug:subject_slug>/<int:pk>/export/",
        views.export_session,
        name="export",
    ),
    # Archive session
    path(
        "<slug:subject_slug>/<int:pk>/archive/",
        views.archive_session,
        name="archive",
    ),
    # Unarchive session
    path(
        "<slug:subject_slug>/<int:pk>/unarchive/",
        views.unarchive_session,
        name="unarchive",
    ),
    # Save message as topic
    path(
        "<slug:subject_slug>/<int:pk>/save-topic/<int:message_id>/",
        views.save_as_topic,
        name="save_topic",
    ),
]
