"""
Dashboard service for aggregating user progress statistics.

Provides methods for computing dashboard data from UserProgress and session models.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from django.db.models import Sum

if TYPE_CHECKING:
    from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


@dataclass
class DashboardSummary:
    """Summary statistics for the dashboard header."""

    total_sessions: int
    total_questions: int
    total_correct: int
    overall_accuracy: float
    current_streak: int
    longest_streak: int
    is_active_today: bool
    subjects_studied: int


@dataclass
class SubjectStats:
    """Statistics for a single subject."""

    subject_id: int
    subject_name: str
    subject_slug: str
    total_sessions: int
    total_questions: int
    total_correct: int
    accuracy: float
    last_studied_at: datetime | None
    exam_sessions: int
    lightning_sessions: int
    qa_sessions: int


@dataclass
class RecentSession:
    """A recent study session."""

    mode: str
    subject_name: str
    subject_slug: str
    started_at: datetime
    score: int | None
    total: int | None
    accuracy: float | None


class DashboardService:
    """
    Service for aggregating dashboard statistics.

    Collects data from UserProgress, StudyStreak, and session models
    to provide comprehensive user learning analytics.
    """

    def __init__(self) -> None:
        """Initialize the dashboard service."""
        self.logger = logging.getLogger(__name__)

    def get_dashboard_summary(self, user: "User") -> DashboardSummary:
        """
        Get summary statistics for the dashboard header.

        Args:
            user: The user to get statistics for.

        Returns:
            DashboardSummary with aggregated stats.
        """
        from apps.accounts.models import StudyStreak, UserProgress

        # Aggregate from UserProgress
        progress_agg = UserProgress.objects.filter(user=user).aggregate(
            total_exam_sessions=Sum("exam_sessions"),
            total_lightning_sessions=Sum("lightning_sessions"),
            total_qa_sessions=Sum("qa_sessions"),
            total_exam_correct=Sum("exam_correct"),
            total_exam_total=Sum("exam_total"),
            total_lightning_correct=Sum("lightning_correct"),
            total_lightning_total=Sum("lightning_total"),
        )

        total_sessions = (
            (progress_agg["total_exam_sessions"] or 0)
            + (progress_agg["total_lightning_sessions"] or 0)
            + (progress_agg["total_qa_sessions"] or 0)
        )
        total_correct = (progress_agg["total_exam_correct"] or 0) + (
            progress_agg["total_lightning_correct"] or 0
        )
        total_questions = (progress_agg["total_exam_total"] or 0) + (
            progress_agg["total_lightning_total"] or 0
        )

        overall_accuracy = 0.0
        if total_questions > 0:
            overall_accuracy = round((total_correct / total_questions) * 100, 1)

        # Get streak info
        try:
            streak = StudyStreak.objects.get(user=user)
            current_streak = streak.current_streak
            longest_streak = streak.longest_streak
            is_active_today = streak.is_active_today
        except StudyStreak.DoesNotExist:
            current_streak = 0
            longest_streak = 0
            is_active_today = False

        # Count subjects studied
        subjects_studied = UserProgress.objects.filter(user=user).count()

        return DashboardSummary(
            total_sessions=total_sessions,
            total_questions=total_questions,
            total_correct=total_correct,
            overall_accuracy=overall_accuracy,
            current_streak=current_streak,
            longest_streak=longest_streak,
            is_active_today=is_active_today,
            subjects_studied=subjects_studied,
        )

    def get_subject_breakdown(self, user: "User") -> list[SubjectStats]:
        """
        Get per-subject performance breakdown.

        Args:
            user: The user to get statistics for.

        Returns:
            List of SubjectStats sorted by last_studied_at descending.
        """
        from apps.accounts.models import UserProgress

        progress_records = UserProgress.objects.filter(user=user).select_related(
            "subject"
        )

        stats = []
        for progress in progress_records:
            total_questions = progress.total_questions
            total_correct = progress.total_correct
            accuracy = 0.0
            if total_questions > 0:
                accuracy = round((total_correct / total_questions) * 100, 1)

            stats.append(
                SubjectStats(
                    subject_id=progress.subject.id,
                    subject_name=progress.subject.name,
                    subject_slug=progress.subject.slug,
                    total_sessions=progress.total_sessions,
                    total_questions=total_questions,
                    total_correct=total_correct,
                    accuracy=accuracy,
                    last_studied_at=progress.last_studied_at,
                    exam_sessions=progress.exam_sessions,
                    lightning_sessions=progress.lightning_sessions,
                    qa_sessions=progress.qa_sessions,
                )
            )

        return stats

    def get_recent_activity(self, user: "User", limit: int = 10) -> list[RecentSession]:
        """
        Get recent session activity across all modes.

        Args:
            user: The user to get activity for.
            limit: Maximum number of sessions to return.

        Returns:
            List of RecentSession sorted by started_at descending.
        """
        from apps.exam.models import ExamSession
        from apps.lightning.models import LightningSession
        from apps.qanda.models import QASession

        recent = []

        # Get recent exam sessions
        exam_sessions = (
            ExamSession.objects.filter(user=user, status=ExamSession.Status.COMPLETED)
            .select_related("subject")
            .order_by("-started_at")[:limit]
        )
        for session in exam_sessions:
            recent.append(
                RecentSession(
                    mode="Exam",
                    subject_name=session.subject.name,
                    subject_slug=session.subject.slug,
                    started_at=session.started_at,
                    score=session.score,
                    total=session.total_answered,
                    accuracy=session.score_percentage,
                )
            )

        # Get recent lightning sessions
        lightning_sessions = (
            LightningSession.objects.filter(
                user=user,
                status__in=[
                    LightningSession.Status.COMPLETED,
                    LightningSession.Status.TIMED_OUT,
                ],
            )
            .select_related("subject")
            .order_by("-started_at")[:limit]
        )
        for session in lightning_sessions:
            recent.append(
                RecentSession(
                    mode="Lightning",
                    subject_name=session.subject.name,
                    subject_slug=session.subject.slug,
                    started_at=session.started_at,
                    score=session.questions_correct,
                    total=session.questions_answered,
                    accuracy=session.accuracy_percentage,
                )
            )

        # Get recent Q&A sessions
        qa_sessions = (
            QASession.objects.filter(user=user)
            .select_related("subject")
            .order_by("-started_at")[:limit]
        )
        for session in qa_sessions:
            recent.append(
                RecentSession(
                    mode="Q&A",
                    subject_name=session.subject.name,
                    subject_slug=session.subject.slug,
                    started_at=session.started_at,
                    score=None,
                    total=session.message_count,
                    accuracy=None,
                )
            )

        # Sort by started_at and limit
        recent.sort(key=lambda x: x.started_at, reverse=True)
        return recent[:limit]

    def get_weakest_subjects(self, user: "User", limit: int = 3) -> list[SubjectStats]:
        """
        Get subjects with lowest accuracy (that have been attempted).

        Args:
            user: The user to get statistics for.
            limit: Maximum number of subjects to return.

        Returns:
            List of SubjectStats sorted by accuracy ascending.
        """
        all_stats = self.get_subject_breakdown(user)

        # Filter to subjects with at least some questions answered
        with_questions = [s for s in all_stats if s.total_questions > 0]

        # Sort by accuracy ascending (weakest first)
        with_questions.sort(key=lambda x: x.accuracy)

        return with_questions[:limit]

    def get_strongest_subjects(
        self, user: "User", limit: int = 3
    ) -> list[SubjectStats]:
        """
        Get subjects with highest accuracy (that have been attempted).

        Args:
            user: The user to get statistics for.
            limit: Maximum number of subjects to return.

        Returns:
            List of SubjectStats sorted by accuracy descending.
        """
        all_stats = self.get_subject_breakdown(user)

        # Filter to subjects with at least some questions answered
        with_questions = [s for s in all_stats if s.total_questions > 0]

        # Sort by accuracy descending (strongest first)
        with_questions.sort(key=lambda x: x.accuracy, reverse=True)

        return with_questions[:limit]


# Singleton instance
_dashboard_service: DashboardService | None = None


def get_dashboard_service() -> DashboardService:
    """Get the singleton dashboard service instance."""
    global _dashboard_service
    if _dashboard_service is None:
        _dashboard_service = DashboardService()
    return _dashboard_service
