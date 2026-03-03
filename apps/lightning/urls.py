"""URL configuration for the lightning app."""

from django.urls import path

from . import views

app_name = "lightning"

urlpatterns = [
    path(
        "<slug:subject_slug>/",
        views.LightningConfigView.as_view(),
        name="config",
    ),
    path(
        "<slug:subject_slug>/start/",
        views.start_lightning,
        name="start",
    ),
    path(
        "<slug:subject_slug>/<int:pk>/",
        views.LightningPlayView.as_view(),
        name="play",
    ),
    path(
        "<slug:subject_slug>/<int:pk>/answer/",
        views.submit_lightning_answer,
        name="answer",
    ),
    path(
        "<slug:subject_slug>/<int:pk>/end/",
        views.end_lightning,
        name="end",
    ),
    path(
        "<slug:subject_slug>/<int:pk>/results/",
        views.LightningResultsView.as_view(),
        name="results",
    ),
    path(
        "<slug:subject_slug>/<int:pk>/time/",
        views.get_time_remaining,
        name="time",
    ),
]
