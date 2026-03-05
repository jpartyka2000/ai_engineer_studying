"""Views for the subjects app."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import Coalesce
from django.views.generic import DetailView

from apps.coding.models import CodingResponse, CodingSession
from apps.exam.models import ExamAnswer, ExamSession

from .models import Subject


class SubjectDetailView(DetailView):
    """Display subject detail with mode selection."""

    model = Subject
    template_name = "subjects/detail.html"
    context_object_name = "subject"

    def get_queryset(self):
        """Only return active subjects."""
        return Subject.objects.filter(is_active=True)


class SubjectStatsView(LoginRequiredMixin, DetailView):
    """Display user statistics for a specific subject."""

    model = Subject
    template_name = "subjects/stats.html"
    context_object_name = "subject"

    def get_queryset(self):
        """Only return active subjects."""
        return Subject.objects.filter(is_active=True)

    def get_context_data(self, **kwargs):
        """Add statistics to the context."""
        context = super().get_context_data(**kwargs)
        subject = self.object
        user = self.request.user

        # Exam statistics
        exam_stats = self._get_exam_stats(user, subject)
        context["exam_stats"] = exam_stats

        # Coding challenge statistics
        coding_stats = self._get_coding_stats(user, subject)
        context["coding_stats"] = coding_stats

        # Combined overview stats
        context["overview"] = self._get_overview_stats(exam_stats, coding_stats)

        # Difficulty breakdown for charts
        context["difficulty_breakdown"] = self._get_difficulty_breakdown(user, subject)

        # Performance over time (last 10 sessions)
        context["performance_history"] = self._get_performance_history(user, subject)

        return context

    def _get_exam_stats(self, user, subject) -> dict:
        """Calculate exam statistics for the user and subject."""
        sessions = ExamSession.objects.filter(
            user=user,
            subject=subject,
            status=ExamSession.Status.COMPLETED,
        )

        if not sessions.exists():
            return {
                "total_sessions": 0,
                "total_questions": 0,
                "correct_answers": 0,
                "accuracy": 0,
                "avg_score": 0,
                "total_time_minutes": 0,
                "best_score": 0,
            }

        # Aggregate session data
        aggregates = sessions.aggregate(
            total_sessions=Count("id"),
            total_correct=Sum("score"),
            total_answered=Sum("total_answered"),
        )

        # Calculate time spent
        total_time = 0
        for session in sessions:
            if session.completed_at and session.started_at:
                delta = session.completed_at - session.started_at
                total_time += delta.total_seconds()

        # Get best score
        best_session = sessions.order_by("-score").first()
        best_score = (
            round(
                (best_session.score / best_session.total_answered) * 100
                if best_session.total_answered > 0
                else 0
            )
            if best_session
            else 0
        )

        total_correct = aggregates["total_correct"] or 0
        total_answered = aggregates["total_answered"] or 0
        accuracy = (
            round((total_correct / total_answered) * 100) if total_answered > 0 else 0
        )

        return {
            "total_sessions": aggregates["total_sessions"],
            "total_questions": total_answered,
            "correct_answers": total_correct,
            "accuracy": accuracy,
            "avg_score": accuracy,  # Same as accuracy for exams
            "total_time_minutes": round(total_time / 60),
            "best_score": best_score,
        }

    def _get_coding_stats(self, user, subject) -> dict:
        """Calculate coding challenge statistics for the user and subject."""
        sessions = CodingSession.objects.filter(
            user=user,
            subject=subject,
            status=CodingSession.Status.COMPLETED,
        )

        if not sessions.exists():
            return {
                "total_sessions": 0,
                "correct_solutions": 0,
                "accuracy": 0,
                "avg_score": 0,
                "total_time_minutes": 0,
                "best_score": 0,
                "avg_correctness": 0,
                "avg_style": 0,
                "avg_completeness": 0,
                "avg_efficiency": 0,
            }

        # Get all responses for these sessions
        responses = CodingResponse.objects.filter(
            session__in=sessions,
            evaluated_at__isnull=False,
        )

        # Aggregate response data
        response_aggregates = responses.aggregate(
            avg_overall=Avg("overall_score"),
            avg_correctness=Avg("correctness_score"),
            avg_style=Avg("style_score"),
            avg_completeness=Avg("completeness_score"),
            avg_efficiency=Avg("efficiency_score"),
            correct_count=Count("id", filter=Q(is_correct=True)),
            total_count=Count("id"),
        )

        # Calculate time spent
        total_time = 0
        for session in sessions:
            if session.completed_at and session.started_at:
                delta = session.completed_at - session.started_at
                total_time += delta.total_seconds()

        # Get best score
        best_response = responses.order_by("-overall_score").first()
        best_score = best_response.overall_score if best_response else 0

        correct_count = response_aggregates["correct_count"] or 0
        total_count = response_aggregates["total_count"] or 0
        accuracy = (
            round((correct_count / total_count) * 100) if total_count > 0 else 0
        )

        return {
            "total_sessions": sessions.count(),
            "correct_solutions": correct_count,
            "accuracy": accuracy,
            "avg_score": round(response_aggregates["avg_overall"] or 0),
            "total_time_minutes": round(total_time / 60),
            "best_score": best_score or 0,
            "avg_correctness": round(response_aggregates["avg_correctness"] or 0),
            "avg_style": round(response_aggregates["avg_style"] or 0),
            "avg_completeness": round(response_aggregates["avg_completeness"] or 0),
            "avg_efficiency": round(response_aggregates["avg_efficiency"] or 0),
        }

    def _get_overview_stats(self, exam_stats: dict, coding_stats: dict) -> dict:
        """Calculate combined overview statistics."""
        total_correct = exam_stats["correct_answers"] + coding_stats["correct_solutions"]
        total_attempts = exam_stats["total_questions"] + coding_stats["total_sessions"]
        total_time = exam_stats["total_time_minutes"] + coding_stats["total_time_minutes"]

        # Calculate overall accuracy
        overall_accuracy = 0
        if total_attempts > 0:
            # Weight exam accuracy by questions, coding by sessions
            exam_weight = exam_stats["total_questions"]
            coding_weight = coding_stats["total_sessions"]
            total_weight = exam_weight + coding_weight
            if total_weight > 0:
                overall_accuracy = round(
                    (exam_stats["accuracy"] * exam_weight + coding_stats["accuracy"] * coding_weight)
                    / total_weight
                )

        return {
            "total_activities": exam_stats["total_sessions"] + coding_stats["total_sessions"],
            "total_correct": total_correct,
            "overall_accuracy": overall_accuracy,
            "total_time_minutes": total_time,
            "total_time_hours": round(total_time / 60, 1),
        }

    def _get_difficulty_breakdown(self, user, subject) -> dict:
        """Get performance breakdown by difficulty level."""
        difficulties = ["beginner", "intermediate", "advanced"]
        breakdown = {}

        for difficulty in difficulties:
            # Exam data for this difficulty
            exam_sessions = ExamSession.objects.filter(
                user=user,
                subject=subject,
                status=ExamSession.Status.COMPLETED,
                difficulty=difficulty,
            )
            exam_agg = exam_sessions.aggregate(
                correct=Sum("score"),
                total=Sum("total_answered"),
            )
            exam_correct = exam_agg["correct"] or 0
            exam_total = exam_agg["total"] or 0

            # Coding data for this difficulty
            coding_sessions = CodingSession.objects.filter(
                user=user,
                subject=subject,
                status=CodingSession.Status.COMPLETED,
                difficulty=difficulty,
            )
            coding_responses = CodingResponse.objects.filter(
                session__in=coding_sessions,
                evaluated_at__isnull=False,
            )
            coding_agg = coding_responses.aggregate(
                correct=Count("id", filter=Q(is_correct=True)),
                total=Count("id"),
            )
            coding_correct = coding_agg["correct"] or 0
            coding_total = coding_agg["total"] or 0

            total_correct = exam_correct + coding_correct
            total_attempts = exam_total + coding_total
            accuracy = (
                round((total_correct / total_attempts) * 100)
                if total_attempts > 0
                else 0
            )

            breakdown[difficulty] = {
                "correct": total_correct,
                "total": total_attempts,
                "accuracy": accuracy,
            }

        return breakdown

    def _get_performance_history(self, user, subject) -> list:
        """Get performance data for the last 10 sessions (for chart)."""
        history = []

        # Get recent exam sessions
        exam_sessions = ExamSession.objects.filter(
            user=user,
            subject=subject,
            status=ExamSession.Status.COMPLETED,
        ).order_by("-completed_at")[:10]

        for session in exam_sessions:
            score_pct = (
                round((session.score / session.total_answered) * 100)
                if session.total_answered > 0
                else 0
            )
            history.append({
                "type": "exam",
                "date": session.completed_at.isoformat() if session.completed_at else "",
                "score": score_pct,
                "label": f"Exam ({session.difficulty[:3].title()})",
            })

        # Get recent coding sessions
        coding_sessions = CodingSession.objects.filter(
            user=user,
            subject=subject,
            status=CodingSession.Status.COMPLETED,
        ).order_by("-completed_at")[:10]

        for session in coding_sessions:
            response = session.responses.order_by("-submission_number").first()
            score = response.overall_score if response else 0
            history.append({
                "type": "coding",
                "date": session.completed_at.isoformat() if session.completed_at else "",
                "score": score,
                "label": f"Code ({session.difficulty[:3].title()})",
            })

        # Sort by date and take last 10
        history.sort(key=lambda x: x["date"], reverse=True)
        return history[:10][::-1]  # Reverse to show oldest first
