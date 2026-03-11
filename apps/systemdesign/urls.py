"""URL configuration for the System Design app."""

from django.urls import path

from . import views

app_name = "systemdesign"

urlpatterns = [
    # Configuration and challenge selection
    path("config/", views.SystemDesignConfigView.as_view(), name="config"),
    path("start/", views.start_session, name="start"),
    path("start/surprise/", views.start_surprise_session, name="surprise"),

    # Active session
    path("<int:pk>/", views.SystemDesignSessionView.as_view(), name="session"),
    path("<int:pk>/save-canvas/", views.save_canvas, name="save_canvas"),
    path("<int:pk>/analyze/", views.analyze_diagram, name="analyze"),
    path("<int:pk>/send-message/", views.send_message, name="send_message"),
    path("<int:pk>/stream/<int:message_id>/", views.stream_response, name="stream"),
    path("<int:pk>/request-hint/", views.request_hint, name="hint"),
    path("<int:pk>/time/", views.get_time_remaining, name="time"),
    path("<int:pk>/submit/", views.submit_design, name="submit"),
    path("<int:pk>/abandon/", views.abandon_session, name="abandon"),

    # Results
    path("<int:pk>/results/", views.SystemDesignResultsView.as_view(), name="results"),
]
