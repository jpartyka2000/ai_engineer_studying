"""Views for the argument app."""

import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, TemplateView

from apps.core.services.claude_service import ClaudeAPIError
from apps.subjects.models import Subject

from .models import ArgumentAnalysis, ArgumentMessage, ArgumentSession
from .services import generate_analysis, generate_initial_prompt, generate_opponent_response

logger = logging.getLogger(__name__)


class ArgumentConfigView(LoginRequiredMixin, TemplateView):
    """Configuration page for starting a new argument."""

    template_name = "argument/config.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subject = get_object_or_404(
            Subject, slug=kwargs["subject_slug"], is_active=True
        )
        context["subject"] = subject
        context["heat_levels"] = ArgumentSession.HeatLevel.choices
        context["difficulty_levels"] = subject.difficulty_levels or [
            "beginner",
            "intermediate",
            "advanced",
        ]
        return context


@login_required
@require_POST
def start_argument(request, subject_slug):
    """Start a new argument session."""
    subject = get_object_or_404(Subject, slug=subject_slug, is_active=True)

    # Get configuration from POST
    difficulty = request.POST.get("difficulty", "intermediate")
    heat_level = request.POST.get("heat_level", ArgumentSession.HeatLevel.COLLEAGUE)

    # Validate heat_level
    valid_heat_levels = [choice[0] for choice in ArgumentSession.HeatLevel.choices]
    if heat_level not in valid_heat_levels:
        heat_level = ArgumentSession.HeatLevel.COLLEAGUE

    try:
        # Generate initial prompt
        initial_prompt = generate_initial_prompt(subject, difficulty)

        # Create session
        session = ArgumentSession.objects.create(
            user=request.user,
            subject=subject,
            difficulty=difficulty,
            heat_level=heat_level,
            initial_prompt=initial_prompt,
        )

        messages.success(
            request,
            _("Argument started! Read the topic and share your opinion."),
        )
        return redirect("argument:session", subject_slug=subject.slug, pk=session.pk)

    except ClaudeAPIError as e:
        logger.exception("Failed to start argument: %s", e)
        messages.error(
            request,
            _("Failed to generate argument topic. Please try again."),
        )
        return redirect("argument:config", subject_slug=subject.slug)


class ArgumentSessionView(LoginRequiredMixin, DetailView):
    """Main argument interface."""

    model = ArgumentSession
    template_name = "argument/session.html"
    context_object_name = "session"

    def get_queryset(self):
        """Filter sessions by user and prefetch messages."""
        return (
            super()
            .get_queryset()
            .filter(user=self.request.user)
            .select_related("subject")
            .prefetch_related("messages")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["messages_list"] = self.object.messages.all()
        context["is_completed"] = self.object.status == ArgumentSession.Status.COMPLETED
        context["heat_level_display"] = self.object.get_heat_level_display()
        return context


@login_required
@require_POST
def submit_response(request, subject_slug, pk):
    """
    Handle user response submission.

    Creates user message and placeholder opponent message,
    then returns stream URL for frontend to connect to.
    """
    session = get_object_or_404(
        ArgumentSession,
        pk=pk,
        user=request.user,
    )

    # Don't allow responses on completed sessions
    if session.status != ArgumentSession.Status.IN_PROGRESS:
        return JsonResponse(
            {"error": "This argument has ended. Start a new one to continue."},
            status=403,
        )

    # Get response from request
    response_text = request.POST.get("response", "").strip()

    if not response_text:
        return JsonResponse({"error": "Response is required"}, status=400)

    # Validate response length
    if len(response_text) > 10000:
        return JsonResponse(
            {"error": "Response is too long (max 10,000 characters)"}, status=400
        )

    # Create user message
    user_message = ArgumentMessage.objects.create(
        session=session,
        role=ArgumentMessage.Role.USER,
        content=response_text,
    )

    # Create placeholder opponent message
    opponent_message = ArgumentMessage.objects.create(
        session=session,
        role=ArgumentMessage.Role.OPPONENT,
        content="",  # Will be filled by streaming
    )

    # Update session message count
    session.update_message_count()

    # Build stream URL
    stream_url = f"/argument/{subject_slug}/{pk}/stream/{opponent_message.id}/"

    return JsonResponse({
        "status": "success",
        "message_id": opponent_message.id,
        "stream_url": stream_url,
        "user_message_id": user_message.id,
    })


@login_required
def stream_response(request, subject_slug, pk, message_id):
    """
    Stream opponent's response using Server-Sent Events (SSE).

    This view establishes an SSE connection and streams the response
    in real-time as it's generated by Claude.
    """
    # Get session and verify ownership
    session = get_object_or_404(
        ArgumentSession,
        pk=pk,
        user=request.user,
    )

    # Don't allow streaming for completed sessions
    if session.status != ArgumentSession.Status.IN_PROGRESS:
        return JsonResponse(
            {"error": "Cannot stream responses for completed arguments"}, status=403
        )

    # Get the opponent message to fill
    message = get_object_or_404(
        ArgumentMessage,
        pk=message_id,
        session=session,
        role=ArgumentMessage.Role.OPPONENT,
    )

    # Get most recent user message
    last_user_msg = (
        session.messages.filter(role=ArgumentMessage.Role.USER)
        .order_by("-created_at")
        .first()
    )

    if not last_user_msg:
        return JsonResponse({"error": "No user message found"}, status=400)

    def event_stream():
        """Generator for SSE events."""
        try:
            full_content = []

            # Stream from Claude
            for chunk in generate_opponent_response(session, last_user_msg.content):
                full_content.append(chunk)
                # SSE format: "data: {json}\n\n"
                data = json.dumps({"chunk": chunk})
                yield f"data: {data}\n\n"

            # Save complete message
            message.content = "".join(full_content)
            message.save()

            # Update session message count
            session.update_message_count()

            # Send completion event
            data = json.dumps({"done": True, "message_id": message.id})
            yield f"data: {data}\n\n"

        except ClaudeAPIError as e:
            logger.exception("Claude API error during streaming: %s", e)
            error_data = json.dumps(
                {"error": "Failed to generate response. Please try again."}
            )
            yield f"data: {error_data}\n\n"
        except Exception as e:
            logger.exception("Unexpected error during streaming: %s", e)
            error_data = json.dumps(
                {"error": "An unexpected error occurred. Please try again."}
            )
            yield f"data: {error_data}\n\n"

    response = StreamingHttpResponse(
        event_stream(),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # Disable nginx buffering
    return response


@login_required
@require_POST
def end_argument(request, subject_slug, pk):
    """
    End the argument and generate analysis.

    Returns JSON with analysis data for frontend to display.
    """
    session = get_object_or_404(
        ArgumentSession,
        pk=pk,
        user=request.user,
    )

    # Don't allow ending already completed sessions
    if session.status != ArgumentSession.Status.IN_PROGRESS:
        return JsonResponse(
            {"error": "This argument has already ended."},
            status=400,
        )

    # Must have at least one exchange
    if session.messages.filter(role=ArgumentMessage.Role.USER).count() < 1:
        return JsonResponse(
            {"error": "You must respond at least once before ending the argument."},
            status=400,
        )

    try:
        # Generate analysis
        analysis_data = generate_analysis(session)

        # Create analysis record
        ArgumentAnalysis.objects.create(
            session=session,
            technical_score=analysis_data["technical_score"],
            temperament_score=analysis_data["temperament_score"],
            focus_score=analysis_data["focus_score"],
            technical_feedback=analysis_data["technical_feedback"],
            temperament_feedback=analysis_data["temperament_feedback"],
            focus_feedback=analysis_data["focus_feedback"],
            overall_feedback=analysis_data["overall_feedback"],
        )

        # Update session status
        session.status = ArgumentSession.Status.COMPLETED
        session.completed_at = timezone.now()
        session.save(update_fields=["status", "completed_at"])

        return JsonResponse({
            "status": "success",
            "redirect_url": f"/argument/{subject_slug}/{pk}/results/",
        })

    except ClaudeAPIError as e:
        logger.exception("Failed to generate analysis: %s", e)
        return JsonResponse(
            {"error": "Failed to analyze the argument. Please try again."},
            status=500,
        )


class ArgumentResultsView(LoginRequiredMixin, DetailView):
    """Display argument analysis results."""

    model = ArgumentSession
    template_name = "argument/results.html"
    context_object_name = "session"

    def get_queryset(self):
        """Filter sessions by user and require completion."""
        return (
            super()
            .get_queryset()
            .filter(
                user=self.request.user,
                status=ArgumentSession.Status.COMPLETED,
            )
            .select_related("subject", "analysis")
            .prefetch_related("messages")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["analysis"] = self.object.analysis
        context["messages_list"] = self.object.messages.all()
        return context
