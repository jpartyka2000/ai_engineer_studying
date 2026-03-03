"""Views for the lightning round app."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, TemplateView

from apps.questions.models import Question
from apps.subjects.models import Subject

from .models import LightningAnswer, LightningSession


class LightningConfigView(LoginRequiredMixin, TemplateView):
    """Configure lightning round settings before starting."""

    template_name = "lightning/config.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subject = get_object_or_404(
            Subject, slug=kwargs["subject_slug"], is_active=True
        )
        context["subject"] = subject

        # Get MC question count for each difficulty
        difficulties = {}
        for level in subject.difficulty_levels:
            count = Question.objects.filter(
                subject=subject,
                difficulty=level,
                question_type="mc",  # Lightning rounds are MC only
                is_active=True,
            ).count()
            difficulties[level] = count

        context["difficulties"] = difficulties
        context["time_limits"] = LightningSession.TIME_LIMIT_CHOICES
        return context


@login_required
@require_POST
def start_lightning(request, subject_slug):
    """Start a new lightning round session."""
    subject = get_object_or_404(Subject, slug=subject_slug, is_active=True)

    # Get configuration from form
    difficulty = request.POST.get("difficulty", "intermediate")
    try:
        time_limit = int(request.POST.get("time_limit", 300))
    except ValueError:
        time_limit = 300

    # Validate time limit
    valid_limits = [choice[0] for choice in LightningSession.TIME_LIMIT_CHOICES]
    if time_limit not in valid_limits:
        time_limit = 300

    # Check if there are MC questions available
    question_count = Question.objects.filter(
        subject=subject,
        difficulty=difficulty,
        question_type="mc",
        is_active=True,
    ).count()

    if question_count == 0:
        messages.error(
            request,
            _(
                "No multiple choice questions available for this subject and difficulty. "
                "Please try a different configuration."
            ),
        )
        return redirect("lightning:config", subject_slug=subject_slug)

    # Create lightning session
    session = LightningSession.objects.create(
        user=request.user,
        subject=subject,
        difficulty=difficulty,
        time_limit_seconds=time_limit,
    )

    return redirect("lightning:play", subject_slug=subject_slug, pk=session.pk)


class LightningPlayView(LoginRequiredMixin, DetailView):
    """Main lightning round gameplay view."""

    model = LightningSession
    template_name = "lightning/play.html"
    context_object_name = "session"

    def get_queryset(self):
        return LightningSession.objects.filter(
            user=self.request.user,
            status=LightningSession.Status.IN_PROGRESS,
        ).select_related("subject")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.object

        # Check if time is up
        if session.is_time_up:
            session.end_session(timed_out=True)
            session.save()
            return context

        # Get a new random question that hasn't been answered yet
        answered_question_ids = session.answers.values_list("question_id", flat=True)
        available_questions = Question.objects.filter(
            subject=session.subject,
            difficulty=session.difficulty,
            question_type="mc",
            is_active=True,
        ).exclude(id__in=answered_question_ids)

        if available_questions.exists():
            question = available_questions.order_by("?").first()
            context["question"] = question
            context["question_number"] = session.questions_answered + 1
        else:
            # No more questions available
            context["no_more_questions"] = True

        context["time_remaining"] = session.time_remaining_seconds
        return context


@login_required
@require_POST
def submit_lightning_answer(request, subject_slug, pk):
    """Submit an answer in lightning round with immediate feedback."""
    session = get_object_or_404(
        LightningSession,
        pk=pk,
        user=request.user,
        status=LightningSession.Status.IN_PROGRESS,
    )

    # Check if time is up
    if session.is_time_up:
        session.end_session(timed_out=True)
        session.save()
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "status": "time_up",
                    "redirect": session.get_results_url(),
                }
            )
        return redirect("lightning:results", subject_slug=subject_slug, pk=pk)

    # Get the question
    question_id = request.POST.get("question_id")
    user_answer = request.POST.get("answer", "").strip().upper()
    response_time_ms = int(request.POST.get("response_time_ms", 0))

    question = get_object_or_404(Question, pk=question_id)

    # Check if correct
    is_correct = user_answer == question.correct_answer.strip().upper()

    # Record the answer
    LightningAnswer.objects.create(
        session=session,
        question=question,
        user_answer=user_answer,
        is_correct=is_correct,
        response_time_ms=response_time_ms,
    )

    # Update session stats
    session.record_answer(is_correct)
    session.save()

    # Return JSON for HTMX/AJAX
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse(
            {
                "status": "ok",
                "is_correct": is_correct,
                "correct_answer": question.correct_answer,
                "explanation": question.explanation,
                "questions_answered": session.questions_answered,
                "questions_correct": session.questions_correct,
                "current_streak": session.current_streak,
                "best_streak": session.best_streak,
                "accuracy": session.accuracy_percentage,
            }
        )

    # Non-AJAX fallback
    return redirect("lightning:play", subject_slug=subject_slug, pk=pk)


@login_required
@require_POST
def end_lightning(request, subject_slug, pk):
    """Manually end a lightning round session."""
    session = get_object_or_404(
        LightningSession,
        pk=pk,
        user=request.user,
        status=LightningSession.Status.IN_PROGRESS,
    )

    session.end_session(timed_out=False)
    session.save()

    messages.success(request, _("Lightning round completed!"))
    return redirect("lightning:results", subject_slug=subject_slug, pk=pk)


class LightningResultsView(LoginRequiredMixin, DetailView):
    """Display lightning round results."""

    model = LightningSession
    template_name = "lightning/results.html"
    context_object_name = "session"

    def get_queryset(self):
        return (
            LightningSession.objects.filter(
                user=self.request.user,
            )
            .exclude(status=LightningSession.Status.IN_PROGRESS)
            .select_related("subject")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.object
        answers = session.answers.select_related("question").order_by("answered_at")

        context["answers"] = answers
        context["correct_count"] = answers.filter(is_correct=True).count()
        context["incorrect_count"] = answers.filter(is_correct=False).count()

        # Calculate average response time
        if answers.exists():
            total_time = sum(a.response_time_ms for a in answers)
            context["avg_response_time_ms"] = total_time // answers.count()
        else:
            context["avg_response_time_ms"] = 0

        return context


@login_required
def get_time_remaining(request, subject_slug, pk):
    """API endpoint to get remaining time for a session."""
    session = get_object_or_404(
        LightningSession,
        pk=pk,
        user=request.user,
    )

    if session.is_time_up and session.status == LightningSession.Status.IN_PROGRESS:
        session.end_session(timed_out=True)
        session.save()

    return JsonResponse(
        {
            "time_remaining": session.time_remaining_seconds,
            "is_time_up": session.is_time_up,
            "status": session.status,
        }
    )
