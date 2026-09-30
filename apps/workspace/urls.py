"""URL routing for workspace mode.

Deliberately not subject-scoped, following ``apps/systemdesign/urls.py``. A single
exercise spans FastAPI, Docker, Postgres and pytest at once, so a ``<subject_slug>``
in the path would be a lie.
"""

from django.urls import path

from apps.workspace import views

app_name = "workspace"

urlpatterns = [
    path("", views.WorkspaceCatalogView.as_view(), name="catalog"),
    path("doctor/", views.doctor_check, name="doctor"),
    path("history/", views.WorkspaceHistoryView.as_view(), name="history"),
    path("exercise/<slug:slug>/", views.WorkspaceExerciseDetailView.as_view(), name="exercise"),
    path("exercise/<slug:slug>/start/", views.start_session, name="start"),
    path("<int:pk>/prepare/", views.WorkspacePrepareView.as_view(), name="prepare"),
    path("<int:pk>/containers/", views.start_containers, name="containers"),
    path("<int:pk>/begin/", views.begin_session, name="begin"),
    path("<int:pk>/", views.WorkspaceSessionView.as_view(), name="session"),
    path("<int:pk>/heartbeat/", views.heartbeat, name="heartbeat"),
    path("<int:pk>/tree/", views.file_tree, name="tree"),
    path("<int:pk>/file/", views.file_preview, name="file"),
    path("<int:pk>/notes/", views.save_notes, name="save_notes"),
    path("<int:pk>/hint/", views.reveal_hint, name="hint"),
    path("<int:pk>/submit/", views.submit_work, name="submit"),
    path("<int:pk>/grade-status/", views.grade_status, name="grade_status"),
    path("<int:pk>/regrade/", views.regrade, name="regrade"),
    path("<int:pk>/abandon/", views.abandon_session, name="abandon"),
    path("<int:pk>/teardown/", views.teardown_workspace, name="teardown"),
    path("<int:pk>/results/", views.WorkspaceResultsView.as_view(), name="results"),
]
