"""Views for the equations (Can I Math?) app."""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, TemplateView

from apps.core.services.llm_service import LLMAPIError
from apps.subjects.models import Subject

from .models import MathAnswer, MathProblem, MathSession, MathSessionProblem
from .services.equation_evaluator import get_equation_evaluator
from .services.equation_generator import get_equation_generator

logger = logging.getLogger(__name__)


class MathConfigView(LoginRequiredMixin, TemplateView):
    """Configure math session settings before starting."""

    template_name = "equations/config.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subject = get_object_or_404(
            Subject, slug=kwargs["subject_slug"], is_active=True
        )
        context["subject"] = subject
        context["difficulties"] = MathProblem.Difficulty.choices
        context["problem_types"] = MathProblem.ProblemType.choices

        # Check if there are existing problems for this subject
        context["existing_problem_count"] = MathProblem.objects.filter(
            subject=subject, is_active=True
        ).count()

        # LLM provider options
        context["llm_providers"] = [
            ("claude", "Claude (Anthropic)"),
            ("openai", "OpenAI GPT"),
        ]

        return context


@login_required
@require_POST
def start_math_session(request, subject_slug):
    """Start a new math practice session."""
    subject = get_object_or_404(Subject, slug=subject_slug, is_active=True)

    # Get configuration from form
    difficulty = request.POST.get("difficulty", "intermediate")
    problem_types = request.POST.getlist("problem_types")
    num_problems = int(request.POST.get("num_problems", 10))
    topic_filter = request.POST.get("topic", "").strip()
    generate_new = request.POST.get("generate_new") == "on"
    llm_provider = request.POST.get("llm_provider", "openai")

    # Default to all problem types if none selected
    if not problem_types:
        problem_types = ["complete", "solve", "mc"]

    # Clamp num_problems
    num_problems = max(1, min(50, num_problems))

    try:
        # Get or generate problems
        if generate_new:
            # Generate new problems with selected LLM provider
            generator = get_equation_generator(provider=llm_provider)
            # Pick a problem type for generation
            gen_type = problem_types[0] if problem_types else "complete"
            generated = generator.generate_problems(
                subject=subject,
                topic=topic_filter or subject.name,
                problem_type=gen_type,
                difficulty=difficulty,
                num_problems=num_problems,
            )
            saved = generator.save_problems(generated, subject)
            if saved:
                problems = saved
            else:
                # Fallback to existing
                problems = list(
                    MathProblem.objects.filter(
                        subject=subject,
                        is_active=True,
                        difficulty=difficulty,
                        problem_type__in=problem_types,
                    ).order_by("?")[:num_problems]
                )
        else:
            # Use existing problems
            queryset = MathProblem.objects.filter(
                subject=subject,
                is_active=True,
                problem_type__in=problem_types,
            )
            if difficulty != "any":
                queryset = queryset.filter(difficulty=difficulty)
            if topic_filter:
                queryset = queryset.filter(topic__icontains=topic_filter)

            problems = list(queryset.order_by("?")[:num_problems])

        if not problems:
            messages.warning(
                request,
                _("No problems found for your criteria. Try generating new problems."),
            )
            return redirect("equations:config", subject_slug=subject_slug)

        # Create session
        session = MathSession.objects.create(
            user=request.user,
            subject=subject,
            difficulty=difficulty,
            problem_types=problem_types,
            topic_filter=topic_filter,
            llm_provider=llm_provider,
            total_problems=len(problems),
        )

        # Link problems to session with ordering
        for i, problem in enumerate(problems):
            MathSessionProblem.objects.create(
                session=session,
                problem=problem,
                order=i,
            )

        return redirect("equations:problem", subject_slug=subject_slug, pk=session.pk)

    except LLMAPIError as e:
        logger.error("LLM API error in math session: %s", str(e))
        error_msg = str(e)
        if "credit balance" in error_msg.lower() or "billing" in error_msg.lower():
            messages.error(
                request,
                _("API credits are insufficient. Please uncheck 'Generate new problems with AI' to use existing problems, or add credits to your API account."),
            )
        elif "quota" in error_msg.lower() or "rate" in error_msg.lower():
            messages.error(
                request,
                _("API rate limit reached. Please try again later or use existing problems."),
            )
        else:
            messages.error(
                request,
                _("Failed to generate problems with AI. Please try using existing problems or a different AI provider."),
            )
        return redirect("equations:config", subject_slug=subject_slug)
    except Exception as e:
        logger.exception("Failed to start math session: %s", str(e))
        messages.error(
            request,
            _("An error occurred while starting the session. Please try again."),
        )
        return redirect("equations:config", subject_slug=subject_slug)


class MathProblemView(LoginRequiredMixin, DetailView):
    """Display a math problem for solving."""

    model = MathSession
    template_name = "equations/problem.html"
    context_object_name = "session"

    def get_queryset(self):
        return MathSession.objects.filter(
            user=self.request.user,
            status=MathSession.Status.IN_PROGRESS,
        ).select_related("subject")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.object

        # Get current problem
        current_problem = session.get_current_problem()
        context["problem"] = current_problem
        context["problem_number"] = session.current_problem_index + 1

        # Get hints already revealed for this problem
        existing_answer = session.answers.filter(problem=current_problem).first()
        hints_used = existing_answer.hints_used if existing_answer else 0
        context["hints_used"] = hints_used
        context["available_hints"] = current_problem.hints[:hints_used] if current_problem else []
        context["has_more_hints"] = (
            current_problem and hints_used < len(current_problem.hints)
        )
        context["total_hints"] = len(current_problem.hints) if current_problem else 0

        # Progress info
        context["progress_percentage"] = session.progress_percentage

        return context


@login_required
@require_POST
def submit_answer(request, subject_slug, pk):
    """Submit an answer for evaluation."""
    session = get_object_or_404(
        MathSession,
        pk=pk,
        user=request.user,
        status=MathSession.Status.IN_PROGRESS,
    )

    current_problem = session.get_current_problem()
    if not current_problem:
        messages.error(request, _("No problem found."))
        return redirect("equations:problem", subject_slug=subject_slug, pk=pk)

    # Get user's answer
    user_answer_latex = request.POST.get("answer_latex", "").strip()
    selected_option = request.POST.get("selected_option", "").strip()
    time_taken = int(request.POST.get("time_taken", 0))

    # Get existing hints used
    existing_answer = session.answers.filter(problem=current_problem).first()
    hints_used = existing_answer.hints_used if existing_answer else 0

    # For MC problems, require option selection
    if current_problem.problem_type == MathProblem.ProblemType.MULTIPLE_CHOICE:
        if not selected_option:
            messages.error(request, _("Please select an option."))
            return redirect("equations:problem", subject_slug=subject_slug, pk=pk)
    else:
        # For other types, require LaTeX input
        if not user_answer_latex:
            messages.error(request, _("Please enter your answer."))
            return redirect("equations:problem", subject_slug=subject_slug, pk=pk)

    try:
        # Evaluate the answer using the session's LLM provider
        evaluator = get_equation_evaluator(provider=session.llm_provider)
        result = evaluator.evaluate_answer(
            problem=current_problem,
            user_answer_latex=user_answer_latex,
            selected_option=selected_option,
        )

        # Create or update answer record
        if existing_answer:
            answer = existing_answer
            answer.user_answer_latex = user_answer_latex
            answer.selected_option = selected_option
            answer.time_taken_seconds = time_taken
        else:
            answer = MathAnswer(
                session=session,
                problem=current_problem,
                user_answer_latex=user_answer_latex,
                selected_option=selected_option,
                hints_used=hints_used,
                time_taken_seconds=time_taken,
            )

        # Save evaluation results
        evaluator.save_evaluation(answer, result)

        # Update session score
        if result.is_correct:
            session.score += 1
        session.total_points += result.partial_credit
        session.save()

        # Move to next problem or complete
        session.current_problem_index += 1
        if session.current_problem_index >= session.total_problems:
            session.status = MathSession.Status.COMPLETED
            session.completed_at = timezone.now()
            session.save()
            messages.success(request, _("Session complete!"))
            return redirect("equations:results", subject_slug=subject_slug, pk=pk)

        session.save()

        # Show feedback and continue
        if result.is_correct:
            messages.success(request, _("Correct!"))
        elif result.partial_credit > 0:
            messages.warning(
                request,
                _(f"Partially correct ({int(result.partial_credit * 100)}% credit)."),
            )
        else:
            messages.error(request, _("Incorrect."))

        return redirect("equations:problem", subject_slug=subject_slug, pk=pk)

    except Exception as e:
        logger.exception("Failed to evaluate answer: %s", str(e))
        messages.error(
            request,
            _("An error occurred during evaluation. Please try again."),
        )
        return redirect("equations:problem", subject_slug=subject_slug, pk=pk)


@login_required
@require_POST
def reveal_hint(request, subject_slug, pk):
    """Reveal the next hint (HTMX endpoint)."""
    session = get_object_or_404(
        MathSession,
        pk=pk,
        user=request.user,
        status=MathSession.Status.IN_PROGRESS,
    )

    current_problem = session.get_current_problem()
    if not current_problem or not current_problem.hints:
        return HttpResponse("No hints available", status=400)

    # Get or create answer to track hints
    answer, created = MathAnswer.objects.get_or_create(
        session=session,
        problem=current_problem,
        defaults={"user_answer_latex": ""},
    )

    if answer.hints_used < len(current_problem.hints):
        answer.hints_used += 1
        answer.save(update_fields=["hints_used"])

        hint = current_problem.hints[answer.hints_used - 1]
        return render(
            request,
            "equations/partials/hint.html",
            {
                "hint": hint,
                "hint_number": answer.hints_used,
                "has_more": answer.hints_used < len(current_problem.hints),
            },
        )

    return HttpResponse("No more hints", status=400)


@login_required
@require_POST
def skip_problem(request, subject_slug, pk):
    """Skip the current problem."""
    session = get_object_or_404(
        MathSession,
        pk=pk,
        user=request.user,
        status=MathSession.Status.IN_PROGRESS,
    )

    current_problem = session.get_current_problem()
    if current_problem:
        # Record as skipped (no answer, no credit)
        MathAnswer.objects.get_or_create(
            session=session,
            problem=current_problem,
            defaults={
                "user_answer_latex": "[SKIPPED]",
                "is_correct": False,
                "partial_credit": 0.0,
                "feedback": "Problem skipped.",
            },
        )

    # Move to next
    session.current_problem_index += 1
    if session.current_problem_index >= session.total_problems:
        session.status = MathSession.Status.COMPLETED
        session.completed_at = timezone.now()
        messages.info(request, _("Session complete."))
        session.save()
        return redirect("equations:results", subject_slug=subject_slug, pk=pk)

    session.save()
    return redirect("equations:problem", subject_slug=subject_slug, pk=pk)


@login_required
@require_POST
def abandon_session(request, subject_slug, pk):
    """Abandon the current session."""
    session = get_object_or_404(
        MathSession,
        pk=pk,
        user=request.user,
        status=MathSession.Status.IN_PROGRESS,
    )

    session.status = MathSession.Status.ABANDONED
    session.save(update_fields=["status"])

    messages.info(request, _("Session abandoned."))
    return redirect("subjects:detail", slug=subject_slug)


class MathResultsView(LoginRequiredMixin, DetailView):
    """Display session results."""

    model = MathSession
    template_name = "equations/results.html"
    context_object_name = "session"

    def get_queryset(self):
        return MathSession.objects.filter(
            user=self.request.user,
            status__in=[MathSession.Status.COMPLETED, MathSession.Status.ABANDONED],
        ).select_related("subject")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.object

        # Get all answers with problems
        answers = session.answers.select_related("problem").order_by("answered_at")
        context["answers"] = answers

        # Calculate stats
        context["accuracy"] = session.accuracy_percentage
        context["total_points"] = session.total_points
        context["max_points"] = session.total_problems

        return context
