"""
Signal handlers for updating user progress and study streaks.

Listens to session completion events and updates UserProgress and StudyStreak models.
"""

import logging
from datetime import date

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.accounts.models import StudyStreak, UserProgress

logger = logging.getLogger(__name__)


def _update_study_streak(user) -> None:
    """
    Update the study streak for a user.

    Creates StudyStreak if it doesn't exist, then records today's activity.
    """
    streak, created = StudyStreak.objects.get_or_create(user=user)
    streak.record_activity(date.today())


def _get_or_create_progress(user, subject) -> UserProgress:
    """Get or create a UserProgress record for user+subject."""
    progress, created = UserProgress.objects.get_or_create(
        user=user,
        subject=subject,
    )
    return progress


@receiver(post_save, sender="exam.ExamSession")
def update_progress_on_exam_complete(sender, instance, created, **kwargs):
    """
    Update UserProgress when an exam session is completed.

    Only triggers when status changes to COMPLETED.
    Practice mode sessions are excluded from stats.
    """
    from apps.exam.models import ExamSession

    if instance.status != ExamSession.Status.COMPLETED:
        return

    # Skip practice mode sessions - they don't affect stats
    if instance.is_practice:
        logger.info(
            "Practice mode exam completed for user %s, subject %s (not counted in stats)",
            instance.user.username,
            instance.subject.name,
        )
        return

    # Check if this is the first time becoming completed
    # by seeing if we've already counted this session
    progress = _get_or_create_progress(instance.user, instance.subject)

    # We need to track which sessions we've already processed
    # to avoid double-counting on repeated saves.
    # Use a simple approach: check if exam_sessions count matches expected
    # Exclude practice sessions from the count
    completed_count = ExamSession.objects.filter(
        user=instance.user,
        subject=instance.subject,
        status=ExamSession.Status.COMPLETED,
        is_practice=False,
    ).count()

    if completed_count > progress.exam_sessions:
        # This is a new completion - update progress
        progress.exam_sessions = completed_count

        # Recalculate totals from all completed sessions for this subject
        # Exclude practice sessions
        from django.db.models import Sum

        agg = ExamSession.objects.filter(
            user=instance.user,
            subject=instance.subject,
            status=ExamSession.Status.COMPLETED,
            is_practice=False,
        ).aggregate(
            total_correct=Sum("score"),
            total_answered=Sum("total_answered"),
        )

        progress.exam_correct = agg["total_correct"] or 0
        progress.exam_total = agg["total_answered"] or 0
        progress.last_studied_at = timezone.now()
        progress.save()

        # Update streak
        _update_study_streak(instance.user)
        logger.info(
            "Updated progress for user %s, subject %s (exam completed)",
            instance.user.username,
            instance.subject.name,
        )


@receiver(post_save, sender="lightning.LightningSession")
def update_progress_on_lightning_complete(sender, instance, created, **kwargs):
    """
    Update UserProgress when a lightning session is completed or times out.

    Triggers when status changes to COMPLETED or TIMED_OUT.
    """
    from apps.lightning.models import LightningSession

    if instance.status not in [
        LightningSession.Status.COMPLETED,
        LightningSession.Status.TIMED_OUT,
    ]:
        return

    progress = _get_or_create_progress(instance.user, instance.subject)

    # Count completed lightning sessions
    completed_count = LightningSession.objects.filter(
        user=instance.user,
        subject=instance.subject,
        status__in=[
            LightningSession.Status.COMPLETED,
            LightningSession.Status.TIMED_OUT,
        ],
    ).count()

    if completed_count > progress.lightning_sessions:
        # This is a new completion - update progress
        progress.lightning_sessions = completed_count

        # Recalculate totals from all completed sessions for this subject
        from django.db.models import Max, Sum

        agg = LightningSession.objects.filter(
            user=instance.user,
            subject=instance.subject,
            status__in=[
                LightningSession.Status.COMPLETED,
                LightningSession.Status.TIMED_OUT,
            ],
        ).aggregate(
            total_correct=Sum("questions_correct"),
            total_answered=Sum("questions_answered"),
            best_streak=Max("best_streak"),
        )

        progress.lightning_correct = agg["total_correct"] or 0
        progress.lightning_total = agg["total_answered"] or 0
        progress.lightning_best_streak = agg["best_streak"] or 0
        progress.last_studied_at = timezone.now()
        progress.save()

        # Update streak
        _update_study_streak(instance.user)
        logger.info(
            "Updated progress for user %s, subject %s (lightning completed)",
            instance.user.username,
            instance.subject.name,
        )


@receiver(post_save, sender="qanda.QASession")
def update_progress_on_qa_session(sender, instance, created, **kwargs):
    """
    Update UserProgress when a Q&A session is created.

    Only triggers on new session creation (not updates).
    """
    if not created:
        return

    progress = _get_or_create_progress(instance.user, instance.subject)

    # Simply count Q&A sessions
    from apps.qanda.models import QASession

    qa_count = QASession.objects.filter(
        user=instance.user,
        subject=instance.subject,
    ).count()

    progress.qa_sessions = qa_count
    progress.last_studied_at = timezone.now()
    progress.save()

    # Update streak
    _update_study_streak(instance.user)
    logger.info(
        "Updated progress for user %s, subject %s (Q&A session created)",
        instance.user.username,
        instance.subject.name,
    )


@receiver(post_save, sender="argument.ArgumentSession")
def update_progress_on_argument_complete(sender, instance, created, **kwargs):
    """
    Update UserProgress when an argument session is completed.

    Only triggers when status changes to COMPLETED and has analysis.
    """
    from apps.argument.models import ArgumentSession

    if instance.status != ArgumentSession.Status.COMPLETED:
        return

    # Check if analysis exists (completion with analysis)
    if not hasattr(instance, "analysis"):
        return

    progress = _get_or_create_progress(instance.user, instance.subject)

    # Count completed argument sessions for this subject
    completed_count = ArgumentSession.objects.filter(
        user=instance.user,
        subject=instance.subject,
        status=ArgumentSession.Status.COMPLETED,
    ).count()

    if completed_count > progress.argument_sessions:
        # This is a new completion - update progress
        progress.argument_sessions = completed_count

        # Calculate average scores from all completed sessions with analysis
        from django.db.models import Avg

        from apps.argument.models import ArgumentAnalysis

        agg = ArgumentAnalysis.objects.filter(
            session__user=instance.user,
            session__subject=instance.subject,
            session__status=ArgumentSession.Status.COMPLETED,
        ).aggregate(
            avg_technical=Avg("technical_score"),
            avg_temperament=Avg("temperament_score"),
            avg_focus=Avg("focus_score"),
        )

        progress.argument_avg_technical = round(agg["avg_technical"] or 0.0, 1)
        progress.argument_avg_temperament = round(agg["avg_temperament"] or 0.0, 1)
        progress.argument_avg_focus = round(agg["avg_focus"] or 0.0, 1)
        progress.last_studied_at = timezone.now()
        progress.save()

        # Update streak
        _update_study_streak(instance.user)
        logger.info(
            "Updated progress for user %s, subject %s (argument completed)",
            instance.user.username,
            instance.subject.name,
        )
