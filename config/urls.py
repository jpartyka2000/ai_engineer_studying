"""
URL configuration for AI Interview Prep project.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("subject/", include("apps.subjects.urls")),
    path("accounts/", include("apps.accounts.urls")),
]
