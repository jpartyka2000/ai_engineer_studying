"""URL configuration for the readiness app."""

from django.urls import path

from apps.readiness import views

app_name = "readiness"

urlpatterns = [
    path("", views.ReadinessOverviewView.as_view(), name="overview"),
]
