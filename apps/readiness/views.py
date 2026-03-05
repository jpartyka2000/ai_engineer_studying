"""Views for the readiness app."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.readiness.services import get_readiness_service, get_study_plan_service


class ReadinessOverviewView(LoginRequiredMixin, TemplateView):
    """
    Main readiness dashboard showing assessment and recommendations.
    """

    template_name = "readiness/overview.html"

    def get_context_data(self, **kwargs):
        """Add readiness assessment to context."""
        context = super().get_context_data(**kwargs)

        # Get role level from query params or default
        role_level = self.request.GET.get("role", "entry")
        if role_level not in ["entry", "senior", "principal"]:
            role_level = "entry"

        # Calculate readiness
        readiness_service = get_readiness_service()
        assessment = readiness_service.calculate_readiness(
            user=self.request.user,
            role_level=role_level,
        )

        # Generate track-specific study recommendations
        study_plan_service = get_study_plan_service()
        track_recommendations = study_plan_service.generate_track_recommendations(
            assessment=assessment,
            max_per_track=15,
        )
        # Also keep combined recommendations for backward compatibility
        assessment.recommendations = study_plan_service.generate_recommendations(
            assessment=assessment,
            max_recommendations=5,
        )

        # Build mode data for template
        mode_data = []
        for mode_name in ["coding", "exam", "argument", "lightning"]:
            perf = assessment.mode_performances.get(mode_name)
            if perf:
                weight_pct = readiness_service.MODE_WEIGHTS[mode_name] * 100
                mode_data.append(
                    {
                        "name": mode_name.title(),
                        "slug": mode_name,
                        "weight": weight_pct,
                        "accuracy": perf.accuracy,
                        "sessions": perf.sessions_count,
                        "questions": perf.total_attempted,
                    }
                )

        # Build category data for template
        category_data = []
        for cat_name, cat_ready in sorted(assessment.category_readiness.items()):
            category_data.append(
                {
                    "name": cat_name,
                    "required": cat_ready.required,
                    "score": cat_ready.score,
                    "is_covered": cat_ready.is_covered,
                    "subjects_attempted": len(cat_ready.subjects_attempted),
                    "subjects_total": len(cat_ready.subjects_in_category),
                    "gap_subjects": cat_ready.gap_subjects,
                }
            )

        # Build difficulty data for template
        difficulty_data = []
        for diff in ["beginner", "intermediate", "advanced"]:
            diff_ready = assessment.difficulty_readiness.get(diff)
            if diff_ready:
                difficulty_data.append(
                    {
                        "name": diff.title(),
                        "slug": diff,
                        "correct": diff_ready.correct,
                        "total": diff_ready.total,
                        "accuracy": diff_ready.accuracy,
                        "meets_threshold": diff_ready.meets_threshold,
                        "required_threshold": diff_ready.required_threshold,
                    }
                )

        context["assessment"] = assessment
        context["mode_data"] = mode_data
        context["category_data"] = category_data
        context["difficulty_data"] = difficulty_data
        context["track_recommendations"] = track_recommendations
        context["role_levels"] = [
            {"slug": "entry", "name": "Entry-level", "threshold": 70},
            {"slug": "senior", "name": "Senior", "threshold": 80},
            {"slug": "principal", "name": "Principal", "threshold": 90},
        ]
        context["current_role"] = role_level

        return context
