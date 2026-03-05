"""URL configuration for the subjects app."""

from django.urls import path

from . import views

app_name = "subjects"

urlpatterns = [
    path("<slug:slug>/", views.SubjectDetailView.as_view(), name="detail"),
    path("<slug:slug>/stats/", views.SubjectStatsView.as_view(), name="stats"),
]
