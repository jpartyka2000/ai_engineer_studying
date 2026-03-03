"""Views for the core app."""

from django.views.generic import TemplateView

from apps.subjects.models import Subject


class HomeView(TemplateView):
    """Home page view displaying the subject picker."""

    template_name = "core/home.html"

    def get_context_data(self, **kwargs) -> dict:
        """Add subjects grouped by category to the context."""
        context = super().get_context_data(**kwargs)

        # Get all active subjects
        subjects = Subject.objects.filter(is_active=True).order_by("category", "name")

        # Group subjects by category
        categories: dict[str, list[Subject]] = {}
        for subject in subjects:
            if subject.category not in categories:
                categories[subject.category] = []
            categories[subject.category].append(subject)

        context["categories"] = categories
        context["total_subjects"] = subjects.count()

        return context
