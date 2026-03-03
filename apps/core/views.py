"""Views for the core app."""

from django.views.generic import TemplateView


class HomeView(TemplateView):
    """Home page view displaying the subject picker."""

    template_name = "core/home.html"
