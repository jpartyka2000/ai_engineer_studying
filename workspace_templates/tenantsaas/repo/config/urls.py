"""URL routing for the billing platform."""

from django.urls import path

from api import views

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("projects", views.list_projects, name="list-projects"),
    path("usage", views.usage_summary, name="usage-summary"),
    path("invoices", views.list_invoices, name="list-invoices"),
    path("invoices/create", views.create_invoice, name="create-invoice"),
    path("reporting/usage", views.usage_by_project, name="usage-by-project"),
    path("reporting/export/<slug:slug>", views.export_project, name="export-project"),
]
