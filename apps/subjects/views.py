"""Views for the subjects app."""

from django.views.generic import DetailView

from .models import Subject


class SubjectDetailView(DetailView):
    """Display subject detail with mode selection."""

    model = Subject
    template_name = "subjects/detail.html"
    context_object_name = "subject"

    def get_queryset(self):
        """Only return active subjects."""
        return Subject.objects.filter(is_active=True)
