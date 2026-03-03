"""Views for the exam app."""

import random

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, TemplateView

from apps.questions.models import Question
from apps.subjects.models import Subject

from .models import ExamAnswer, ExamSession


class ExamConfigView(LoginRequiredMixin, TemplateView):
    """Configure exam settings before starting."""

    template_name = "exam/config.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subject = get_object_or_404(
            Subject, slug=kwargs["subject_slug"], is_active=True
        )
        context["subject"] = subject

        # Get available question count for each difficulty
        difficulties = {}
        for level in subject.difficulty_levels:
            count = Question.objects.filter(
                subject=subject,
                difficulty=level,
                is_active=True,
            ).count()
            difficulties[level] = count

        context["difficulties"] = difficulties
        context["default_count"] = subject.default_question_count
        return context


@login_required
@require_POST
def start_exam(request, subject_slug):
    """Start a new exam session."""
    subject = get_object_or_404(Subject, slug=subject_slug, is_active=True)

    # Get configuration from form
    difficulty = request.POST.get("difficulty", "intermediate")
    try:
        question_count = int(
            request.POST.get("question_count", subject.default_question_count)
        )
    except ValueError:
        question_count = subject.default_question_count

    # Validate question count
    question_count = max(1, min(question_count, 50))

    # Get available questions
    available_questions = list(
        Question.objects.filter(
            subject=subject,
            difficulty=difficulty,
            is_active=True,
        ).values_list("id", flat=True)
    )

    if len(available_questions) < question_count:
        messages.warning(
            request,
            _(
                f"Only {len(available_questions)} questions available for {difficulty} difficulty."
            ),
        )
        question_count = len(available_questions)

    if question_count == 0:
        messages.error(
            request,
            _(
                "No questions available for this subject and difficulty. Please try a different configuration."
            ),
        )
        return redirect("exam:config", subject_slug=subject_slug)

    # Select random questions
    selected_ids = random.sample(available_questions, question_count)

    # Create exam session
    session = ExamSession.objects.create(
        user=request.user,
        subject=subject,
        difficulty=difficulty,
        question_count=question_count,
    )

    # Create exam answers (question slots)
    questions = Question.objects.filter(id__in=selected_ids)
    for i, question in enumerate(questions):
        ExamAnswer.objects.create(
            session=session,
            question=question,
            order=i,
        )

    return redirect("exam:question", subject_slug=subject_slug, pk=session.pk)


class ExamQuestionView(LoginRequiredMixin, DetailView):
    """Display current question in an exam session."""

    model = ExamSession
    template_name = "exam/question.html"
    context_object_name = "session"

    def get_queryset(self):
        return ExamSession.objects.filter(
            user=self.request.user,
            status=ExamSession.Status.IN_PROGRESS,
        ).select_related("subject")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.object

        # Get current answer slot
        answers = list(session.answers.select_related("question").order_by("order"))
        if session.current_question_index < len(answers):
            current_answer = answers[session.current_question_index]
            context["current_answer"] = current_answer
            context["question"] = current_answer.question
            context["question_number"] = session.current_question_index + 1
            context["total_questions"] = session.question_count
            context["progress_percent"] = int(
                (session.current_question_index / session.question_count) * 100
            )
        else:
            # All questions answered, redirect to submit
            context["all_answered"] = True

        return context


@login_required
@require_POST
def submit_answer(request, subject_slug, pk):
    """Submit an answer to the current question."""
    session = get_object_or_404(
        ExamSession,
        pk=pk,
        user=request.user,
        status=ExamSession.Status.IN_PROGRESS,
    )

    # Get current answer slot
    answers = list(session.answers.order_by("order"))
    if session.current_question_index >= len(answers):
        return redirect("exam:submit", subject_slug=subject_slug, pk=pk)

    current_answer = answers[session.current_question_index]

    # Update answer
    current_answer.user_answer = request.POST.get("answer", "")
    current_answer.is_flagged = request.POST.get("flag") == "on"
    current_answer.answered_at = timezone.now()

    # Check if correct
    current_answer.check_answer()
    current_answer.save()

    # Update session
    session.current_question_index += 1
    session.total_answered += 1
    if current_answer.is_correct:
        session.score += 1
    session.save()

    # Check if exam is complete
    if session.current_question_index >= session.question_count:
        return redirect("exam:submit", subject_slug=subject_slug, pk=pk)

    return redirect("exam:question", subject_slug=subject_slug, pk=pk)


@login_required
@require_POST
def toggle_flag(request, subject_slug, pk):
    """Toggle the flag status on the current question."""
    session = get_object_or_404(
        ExamSession,
        pk=pk,
        user=request.user,
        status=ExamSession.Status.IN_PROGRESS,
    )

    answers = list(session.answers.order_by("order"))
    if session.current_question_index < len(answers):
        current_answer = answers[session.current_question_index]
        current_answer.is_flagged = not current_answer.is_flagged
        current_answer.save()

    return redirect("exam:question", subject_slug=subject_slug, pk=pk)


class ExamSubmitView(LoginRequiredMixin, DetailView):
    """Confirmation page before submitting the exam."""

    model = ExamSession
    template_name = "exam/submit.html"
    context_object_name = "session"

    def get_queryset(self):
        return ExamSession.objects.filter(
            user=self.request.user,
            status=ExamSession.Status.IN_PROGRESS,
        ).select_related("subject")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.object
        answers = session.answers.select_related("question").order_by("order")

        context["answers"] = answers
        context["flagged_count"] = answers.filter(is_flagged=True).count()
        context["unanswered_count"] = answers.filter(user_answer="").count()

        return context


@login_required
@require_POST
def complete_exam(request, subject_slug, pk):
    """Complete the exam and calculate final score."""
    session = get_object_or_404(
        ExamSession,
        pk=pk,
        user=request.user,
        status=ExamSession.Status.IN_PROGRESS,
    )

    # Mark as completed
    session.status = ExamSession.Status.COMPLETED
    session.completed_at = timezone.now()
    session.save()

    messages.success(request, _("Exam completed! Review your results below."))
    return redirect("exam:results", subject_slug=subject_slug, pk=pk)


class ExamResultsView(LoginRequiredMixin, DetailView):
    """Display exam results and review."""

    model = ExamSession
    template_name = "exam/results.html"
    context_object_name = "session"

    def get_queryset(self):
        return ExamSession.objects.filter(
            user=self.request.user,
            status=ExamSession.Status.COMPLETED,
        ).select_related("subject")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.object
        answers = session.answers.select_related("question").order_by("order")

        context["answers"] = answers
        context["correct_count"] = answers.filter(is_correct=True).count()
        context["incorrect_count"] = answers.filter(is_correct=False).count()
        context["flagged_answers"] = answers.filter(is_flagged=True)

        return context
