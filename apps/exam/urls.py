"""URL configuration for the exam app."""

from django.urls import path

from . import views

app_name = "exam"

urlpatterns = [
    path(
        "<slug:subject_slug>/",
        views.ExamConfigView.as_view(),
        name="config",
    ),
    path(
        "<slug:subject_slug>/start/",
        views.start_exam,
        name="start",
    ),
    path(
        "<slug:subject_slug>/session/<int:pk>/",
        views.ExamQuestionView.as_view(),
        name="question",
    ),
    path(
        "<slug:subject_slug>/session/<int:pk>/answer/",
        views.submit_answer,
        name="answer",
    ),
    path(
        "<slug:subject_slug>/session/<int:pk>/flag/",
        views.toggle_flag,
        name="flag",
    ),
    path(
        "<slug:subject_slug>/session/<int:pk>/submit/",
        views.ExamSubmitView.as_view(),
        name="submit",
    ),
    path(
        "<slug:subject_slug>/session/<int:pk>/complete/",
        views.complete_exam,
        name="complete",
    ),
    path(
        "<slug:subject_slug>/session/<int:pk>/results/",
        views.ExamResultsView.as_view(),
        name="results",
    ),
    path(
        "<slug:subject_slug>/session/<int:pk>/question/<int:question_id>/create-questions/",
        views.create_llm_questions,
        name="create_llm_questions",
    ),
]
