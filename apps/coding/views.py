"""Views for the coding app."""

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

from apps.subjects.models import Subject

from .models import CodingChallenge, CodingSession
from .services.challenge_generator import get_challenge_generator
from .services.code_evaluator import get_code_evaluator

logger = logging.getLogger(__name__)


class CodingConfigView(LoginRequiredMixin, TemplateView):
    """Configure coding challenge settings before starting."""

    template_name = "coding/config.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subject = get_object_or_404(
            Subject, slug=kwargs["subject_slug"], is_active=True
        )
        context["subject"] = subject
        context["languages"] = self._get_available_languages(subject)
        context["difficulties"] = CodingChallenge.Difficulty.choices
        context["challenge_types"] = CodingChallenge.ChallengeType.choices
        return context

    def _get_available_languages(self, subject) -> list[tuple[str, str]]:
        """
        Get available programming languages for this subject.

        Always includes Python. If the subject has a specific coding_language
        (like 'git', 'sql', 'shell'), include that as an option too.
        """
        # Always include Python
        languages = [("python", "Python")]

        # Add subject-specific language if defined
        if subject.coding_language:
            # Map the coding_language to a display name
            language_labels = {
                "git": "Git Commands",
                "sql": "SQL",
                "shell": "Shell/Bash",
                "javascript": "JavaScript",
                "docker": "Docker",
            }
            label = language_labels.get(
                subject.coding_language,
                subject.coding_language.title()
            )
            languages.append((subject.coding_language, label))

        return languages


@login_required
@require_POST
def start_coding_session(request, subject_slug):
    """Start a new coding session with an LLM-generated challenge."""
    subject = get_object_or_404(Subject, slug=subject_slug, is_active=True)

    # Get configuration from form
    difficulty = request.POST.get("difficulty", "intermediate")
    challenge_type = request.POST.get("challenge_type", "implement")
    language = request.POST.get("language", "python")
    topic = request.POST.get("topic", "").strip()

    # Use subject name as topic if not specified
    if not topic:
        topic = f"general {subject.name} concepts"

    # Generate a new challenge using Claude
    try:
        generator = get_challenge_generator()
        generated_challenges = generator.generate_challenges(
            subject=subject,
            topic=topic,
            num_challenges=1,
            difficulty=difficulty,
            challenge_type=challenge_type,
            language=language,
        )

        if not generated_challenges:
            messages.error(
                request,
                _("Failed to generate a challenge. Please try again."),
            )
            return redirect("coding:config", subject_slug=subject_slug)

        # Save the generated challenge
        saved_challenges = generator.save_challenges(generated_challenges, subject)

        if saved_challenges:
            challenge = saved_challenges[0]
        else:
            # Challenge might already exist (duplicate), try to find it
            gen_challenge = generated_challenges[0]
            challenge = CodingChallenge.objects.filter(
                subject=subject,
                title=gen_challenge.title,
            ).first()

            if not challenge:
                # Create it anyway without dedup check
                challenge = CodingChallenge.objects.create(
                    subject=subject,
                    title=gen_challenge.title,
                    description=gen_challenge.description,
                    challenge_type=gen_challenge.challenge_type,
                    language=gen_challenge.language,
                    starter_code=gen_challenge.starter_code,
                    reference_solution=gen_challenge.reference_solution,
                    evaluation_criteria=gen_challenge.evaluation_criteria,
                    expected_output=gen_challenge.expected_output,
                    hints=gen_challenge.hints,
                    difficulty=gen_challenge.difficulty,
                    tags=gen_challenge.tags,
                    estimated_time_minutes=gen_challenge.estimated_time_minutes,
                    source=CodingChallenge.Source.CLAUDE_API,
                )

        # Create session
        session = CodingSession.objects.create(
            user=request.user,
            subject=subject,
            challenge=challenge,
            challenge_type=challenge.challenge_type,
            difficulty=challenge.difficulty,
            language=challenge.language,
            user_code=challenge.starter_code,  # Initialize with starter code
        )

        return redirect("coding:challenge", subject_slug=subject_slug, pk=session.pk)

    except Exception as e:
        logger.exception("Failed to generate coding challenge: %s", str(e))
        messages.error(
            request,
            _("An error occurred while generating the challenge. Please try again."),
        )
        return redirect("coding:config", subject_slug=subject_slug)


class CodingChallengeView(LoginRequiredMixin, DetailView):
    """Display the coding challenge with Monaco editor."""

    model = CodingSession
    template_name = "coding/challenge.html"
    context_object_name = "session"

    def get_queryset(self):
        return CodingSession.objects.filter(
            user=self.request.user,
            status=CodingSession.Status.IN_PROGRESS,
        ).select_related("subject", "challenge")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.object
        challenge = session.challenge

        context["challenge"] = challenge
        context["available_hints"] = challenge.hints[: session.hints_used]
        context["has_more_hints"] = session.hints_used < len(challenge.hints)
        context["total_hints"] = len(challenge.hints)
        context["monaco_language"] = self._get_monaco_language(session.language)

        # Get sample test cases (visible ones)
        context["sample_tests"] = challenge.test_cases.filter(
            is_sample=True, is_hidden=False
        )
        context["has_hidden_tests"] = challenge.test_cases.filter(is_hidden=True).exists()

        return context

    def _get_monaco_language(self, language: str) -> str:
        """Map language to Monaco editor language identifier."""
        mapping = {
            "python": "python",
            "javascript": "javascript",
            "sql": "sql",
            "git": "shell",
            "shell": "shell",
            "docker": "dockerfile",
        }
        return mapping.get(language, "plaintext")


@login_required
@require_POST
def save_draft(request, subject_slug, pk):
    """Save draft code (HTMX endpoint)."""
    session = get_object_or_404(
        CodingSession,
        pk=pk,
        user=request.user,
        status=CodingSession.Status.IN_PROGRESS,
    )

    session.user_code = request.POST.get("code", "")
    session.save(update_fields=["user_code"])

    return HttpResponse("Saved", status=200)


@login_required
@require_POST
def reveal_hint(request, subject_slug, pk):
    """Reveal the next hint (HTMX endpoint)."""
    session = get_object_or_404(
        CodingSession,
        pk=pk,
        user=request.user,
        status=CodingSession.Status.IN_PROGRESS,
    )

    challenge = session.challenge
    if session.hints_used < len(challenge.hints):
        session.hints_used += 1
        session.save(update_fields=["hints_used"])

        # Return the newly revealed hint
        hint = challenge.hints[session.hints_used - 1]
        return render(
            request,
            "coding/partials/hint.html",
            {
                "hint": hint,
                "hint_number": session.hints_used,
                "has_more": session.hints_used < len(challenge.hints),
            },
        )

    return HttpResponse("No more hints", status=400)


@login_required
@require_POST
def submit_code(request, subject_slug, pk):
    """Submit code for evaluation."""
    session = get_object_or_404(
        CodingSession,
        pk=pk,
        user=request.user,
        status=CodingSession.Status.IN_PROGRESS,
    )

    submitted_code = request.POST.get("code", "")

    if not submitted_code.strip():
        messages.error(request, _("Please write some code before submitting."))
        return redirect("coding:challenge", subject_slug=subject_slug, pk=pk)

    # Update session
    session.user_code = submitted_code
    session.status = CodingSession.Status.SUBMITTED
    session.submitted_at = timezone.now()
    session.save()

    # Evaluate with Claude
    try:
        evaluator = get_code_evaluator()
        evaluator.evaluate_submission(session, submitted_code)

        # Mark session as completed
        session.status = CodingSession.Status.COMPLETED
        session.completed_at = timezone.now()
        session.save()

        messages.success(request, _("Your code has been evaluated!"))
        return redirect("coding:results", subject_slug=subject_slug, pk=pk)

    except Exception as e:
        logger.exception("Failed to evaluate code: %s", str(e))
        # Revert status on error
        session.status = CodingSession.Status.IN_PROGRESS
        session.submitted_at = None
        session.save()

        messages.error(
            request,
            _("An error occurred during evaluation. Please try again."),
        )
        return redirect("coding:challenge", subject_slug=subject_slug, pk=pk)


@login_required
@require_POST
def abandon_session(request, subject_slug, pk):
    """Abandon the current coding session."""
    session = get_object_or_404(
        CodingSession,
        pk=pk,
        user=request.user,
        status=CodingSession.Status.IN_PROGRESS,
    )

    session.status = CodingSession.Status.ABANDONED
    session.save(update_fields=["status"])

    messages.info(request, _("Challenge abandoned."))
    return redirect("subjects:detail", slug=subject_slug)


class CodingResultsView(LoginRequiredMixin, DetailView):
    """Display evaluation results."""

    model = CodingSession
    template_name = "coding/results.html"
    context_object_name = "session"

    def get_queryset(self):
        return CodingSession.objects.filter(
            user=self.request.user,
            status=CodingSession.Status.COMPLETED,
        ).select_related("subject", "challenge")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.object

        # Get the latest response
        response = session.responses.order_by("-submission_number").first()
        context["response"] = response

        # Calculate score breakdown for visualization
        if response:
            context["score_breakdown"] = {
                "correctness": response.correctness_score,
                "style": response.style_score,
                "completeness": response.completeness_score,
                "efficiency": response.efficiency_score,
            }

            # Get execution results for test display
            execution_results = response.execution_results.select_related(
                "test_case"
            ).order_by("test_case__order")
            context["execution_results"] = execution_results
            context["tests_total"] = execution_results.count()
            context["tests_passed"] = sum(
                1 for r in execution_results if r.status == "passed"
            )

        return context
