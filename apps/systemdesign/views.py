"""Views for the System Design app."""

import base64
import json
import logging

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import DetailView, TemplateView

from apps.subjects.models import Subject

from .models import (
    DiagramAnalysis,
    SystemDesignChallenge,
    SystemDesignMessage,
    SystemDesignScore,
    SystemDesignSession,
)
from .services.challenge_service import get_challenge_service
from .services.conversation_service import get_conversation_service
from .services.diagram_analyzer import get_diagram_analyzer
from .services.scoring_service import get_scoring_service

logger = logging.getLogger(__name__)


class SystemDesignConfigView(LoginRequiredMixin, TemplateView):
    """Configuration view for selecting a system design challenge."""

    template_name = "systemdesign/config.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get System Design subject
        subject = get_object_or_404(Subject, slug="system-design", is_active=True)
        context["subject"] = subject

        # Get available challenges grouped by difficulty
        service = get_challenge_service()
        challenges = service.get_available_challenges()

        context["beginner_challenges"] = challenges.filter(difficulty="beginner")
        context["intermediate_challenges"] = challenges.filter(difficulty="intermediate")
        context["advanced_challenges"] = challenges.filter(difficulty="advanced")

        # Check for in-progress sessions
        in_progress = SystemDesignSession.objects.filter(
            user=self.request.user,
            status=SystemDesignSession.Status.IN_PROGRESS,
        ).first()
        context["in_progress_session"] = in_progress

        return context


@login_required
@require_POST
def start_session(request: HttpRequest) -> HttpResponse:
    """Start a new system design session with a pre-defined challenge."""
    challenge_slug = request.POST.get("challenge_slug")
    if not challenge_slug:
        return JsonResponse({"error": "Challenge slug required"}, status=400)

    service = get_challenge_service()
    challenge = service.get_challenge_by_slug(challenge_slug)

    if not challenge:
        return JsonResponse({"error": "Challenge not found"}, status=404)

    # Create session
    session = SystemDesignSession.objects.create(
        user=request.user,
        challenge=challenge,
        difficulty=challenge.difficulty,
        time_limit_seconds=challenge.time_limit_seconds,
    )

    # Generate initial interviewer message
    conv_service = get_conversation_service()
    initial_message = conv_service.generate_initial_message(session)

    SystemDesignMessage.objects.create(
        session=session,
        role=SystemDesignMessage.Role.ASSISTANT,
        content=initial_message,
        message_type=SystemDesignMessage.MessageType.INITIAL,
    )

    return redirect("systemdesign:session", pk=session.pk)


@login_required
@require_POST
def start_surprise_session(request: HttpRequest) -> HttpResponse:
    """Start a session with an LLM-generated 'surprise' challenge."""
    difficulty = request.POST.get("difficulty", "intermediate")

    if difficulty not in ["beginner", "intermediate", "advanced"]:
        difficulty = "intermediate"

    # Generate surprise challenge
    service = get_challenge_service()
    try:
        challenge_data = service.generate_surprise_challenge(difficulty)
    except Exception as e:
        logger.exception("Failed to generate surprise challenge")
        return JsonResponse({"error": str(e)}, status=500)

    # Create session with surprise data
    session = SystemDesignSession.objects.create(
        user=request.user,
        challenge=None,  # No pre-defined challenge
        surprise_challenge_data=challenge_data,
        difficulty=difficulty,
        time_limit_seconds=challenge_data.get("time_limit_seconds", 1800),
    )

    # Generate initial message
    conv_service = get_conversation_service()
    initial_message = conv_service.generate_initial_message(session)

    SystemDesignMessage.objects.create(
        session=session,
        role=SystemDesignMessage.Role.ASSISTANT,
        content=initial_message,
        message_type=SystemDesignMessage.MessageType.INITIAL,
    )

    return redirect("systemdesign:session", pk=session.pk)


class SystemDesignSessionView(LoginRequiredMixin, DetailView):
    """Main view for the active system design session."""

    model = SystemDesignSession
    template_name = "systemdesign/session.html"
    context_object_name = "session"

    def get_queryset(self):
        return SystemDesignSession.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.object

        # Check if session has ended
        if session.is_time_up and session.status == SystemDesignSession.Status.IN_PROGRESS:
            # Auto-end session
            session.end_session(SystemDesignSession.Status.TIMED_OUT)
            return redirect("systemdesign:results", pk=session.pk)

        # Get messages
        context["messages"] = session.messages.order_by("created_at")

        # Get latest analysis
        context["latest_analysis"] = session.analyses.order_by("-created_at").first()

        # Time info
        context["time_remaining"] = session.time_remaining_seconds
        context["time_limit"] = session.time_limit_seconds

        # Canvas state for restoration
        context["canvas_state_json"] = json.dumps(session.canvas_state)

        # Challenge info
        context["challenge_title"] = session.effective_challenge_title
        context["description"] = session.effective_description
        context["functional_requirements"] = session.effective_functional_requirements
        context["non_functional_requirements"] = session.effective_non_functional_requirements
        context["constraints"] = session.effective_constraints

        return context

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Check if session already completed
        if self.object.status in [
            SystemDesignSession.Status.COMPLETED,
            SystemDesignSession.Status.TIMED_OUT,
        ]:
            return redirect("systemdesign:results", pk=self.object.pk)

        return super().get(request, *args, **kwargs)


@login_required
@require_POST
def save_canvas(request: HttpRequest, pk: int) -> JsonResponse:
    """Save the current canvas state."""
    session = get_object_or_404(
        SystemDesignSession,
        pk=pk,
        user=request.user,
        status=SystemDesignSession.Status.IN_PROGRESS,
    )

    try:
        data = json.loads(request.body)
        canvas_state = data.get("canvas_state", {})
        canvas_png_b64 = data.get("canvas_png")  # Base64 encoded PNG

        session.canvas_state = canvas_state

        if canvas_png_b64:
            # Decode base64 PNG
            # Remove data URL prefix if present
            if "," in canvas_png_b64:
                canvas_png_b64 = canvas_png_b64.split(",")[1]
            session.canvas_snapshot_png = base64.b64decode(canvas_png_b64)

        session.save(update_fields=["canvas_state", "canvas_snapshot_png"])

        return JsonResponse({"status": "saved"})

    except Exception as e:
        logger.exception("Failed to save canvas: %s", str(e))
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def analyze_diagram(request: HttpRequest, pk: int) -> JsonResponse:
    """Trigger on-demand diagram analysis."""
    session = get_object_or_404(
        SystemDesignSession,
        pk=pk,
        user=request.user,
        status=SystemDesignSession.Status.IN_PROGRESS,
    )

    try:
        data = json.loads(request.body)
        canvas_png_b64 = data.get("canvas_png")
        canvas_state = data.get("canvas_state", {})

        if not canvas_png_b64:
            return JsonResponse({"error": "Canvas PNG required"}, status=400)

        # Decode PNG
        if "," in canvas_png_b64:
            canvas_png_b64 = canvas_png_b64.split(",")[1]
        png_data = base64.b64decode(canvas_png_b64)

        # Run analysis
        analyzer = get_diagram_analyzer()
        analysis = analyzer.analyze_canvas(
            session=session,
            png_data=png_data,
            canvas_json=canvas_state,
            analysis_type=DiagramAnalysis.AnalysisType.ON_DEMAND,
        )

        return JsonResponse({
            "status": "success",
            "analysis": {
                "id": analysis.id,
                "components": analysis.identified_components,
                "connections": analysis.identified_connections,
                "strengths": analysis.strengths,
                "concerns": analysis.concerns,
                "suggestions": analysis.suggestions,
                "overall_impression": analysis.overall_impression,
                "scores": analysis.preliminary_scores,
                "created_at": analysis.created_at.isoformat(),
            }
        })

    except Exception as e:
        logger.exception("Failed to analyze diagram: %s", str(e))
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def send_message(request: HttpRequest, pk: int) -> JsonResponse:
    """Send a message to the interviewer."""
    session = get_object_or_404(
        SystemDesignSession,
        pk=pk,
        user=request.user,
        status=SystemDesignSession.Status.IN_PROGRESS,
    )

    try:
        data = json.loads(request.body)
        content = data.get("content", "").strip()
        message_type = data.get("message_type", "general")

        if not content:
            return JsonResponse({"error": "Message content required"}, status=400)

        # Create user message
        user_message = SystemDesignMessage.objects.create(
            session=session,
            role=SystemDesignMessage.Role.USER,
            content=content,
            message_type=message_type,
        )

        # Create placeholder for assistant response
        assistant_message = SystemDesignMessage.objects.create(
            session=session,
            role=SystemDesignMessage.Role.ASSISTANT,
            content="",
            message_type=message_type,
        )

        # Return stream URL
        stream_url = reverse(
            "systemdesign:stream",
            kwargs={"pk": session.pk, "message_id": assistant_message.pk},
        )

        return JsonResponse({
            "status": "success",
            "user_message_id": user_message.pk,
            "assistant_message_id": assistant_message.pk,
            "stream_url": stream_url,
        })

    except Exception as e:
        logger.exception("Failed to send message: %s", str(e))
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_GET
def stream_response(request: HttpRequest, pk: int, message_id: int) -> StreamingHttpResponse:
    """Stream the interviewer's response via SSE."""
    session = get_object_or_404(
        SystemDesignSession,
        pk=pk,
        user=request.user,
    )

    assistant_message = get_object_or_404(
        SystemDesignMessage,
        pk=message_id,
        session=session,
        role=SystemDesignMessage.Role.ASSISTANT,
    )

    # Get the user message (the one before this assistant message)
    user_message = session.messages.filter(
        created_at__lt=assistant_message.created_at,
        role=SystemDesignMessage.Role.USER,
    ).order_by("-created_at").first()

    if not user_message:
        def error_generator():
            yield 'data: {"error": "No user message found"}\n\n'
        return StreamingHttpResponse(
            error_generator(),
            content_type="text/event-stream",
        )

    def event_stream():
        conv_service = get_conversation_service()
        full_response = ""

        try:
            for chunk in conv_service.stream_response(
                session=session,
                user_message=user_message.content,
                message_type=user_message.message_type,
                include_diagram_context=True,
            ):
                full_response += chunk
                yield f'data: {json.dumps({"chunk": chunk})}\n\n'

            # Save the complete response
            assistant_message.content = full_response
            assistant_message.token_count_estimate = len(full_response) // 4
            assistant_message.save(update_fields=["content", "token_count_estimate"])

            yield f'data: {json.dumps({"done": True})}\n\n'

        except Exception as e:
            logger.exception("Streaming error: %s", str(e))
            yield f'data: {json.dumps({"error": str(e)})}\n\n'

    response = StreamingHttpResponse(
        event_stream(),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@login_required
@require_POST
def request_hint(request: HttpRequest, pk: int) -> JsonResponse:
    """Request a hint from the interviewer."""
    session = get_object_or_404(
        SystemDesignSession,
        pk=pk,
        user=request.user,
        status=SystemDesignSession.Status.IN_PROGRESS,
    )

    # Create hint request message
    user_message = SystemDesignMessage.objects.create(
        session=session,
        role=SystemDesignMessage.Role.USER,
        content="Can you give me a hint on how to proceed?",
        message_type=SystemDesignMessage.MessageType.HINT,
    )

    # Create placeholder for response
    assistant_message = SystemDesignMessage.objects.create(
        session=session,
        role=SystemDesignMessage.Role.ASSISTANT,
        content="",
        message_type=SystemDesignMessage.MessageType.HINT,
    )

    stream_url = reverse(
        "systemdesign:stream",
        kwargs={"pk": session.pk, "message_id": assistant_message.pk},
    )

    return JsonResponse({
        "status": "success",
        "user_message_id": user_message.pk,
        "assistant_message_id": assistant_message.pk,
        "stream_url": stream_url,
    })


@login_required
@require_GET
def get_time_remaining(request: HttpRequest, pk: int) -> JsonResponse:
    """Get the remaining time for a session."""
    session = get_object_or_404(
        SystemDesignSession,
        pk=pk,
        user=request.user,
    )

    return JsonResponse({
        "time_remaining": session.time_remaining_seconds,
        "is_time_up": session.is_time_up,
        "status": session.status,
    })


@login_required
@require_POST
def submit_design(request: HttpRequest, pk: int) -> JsonResponse:
    """Submit the design for final scoring."""
    session = get_object_or_404(
        SystemDesignSession,
        pk=pk,
        user=request.user,
        status=SystemDesignSession.Status.IN_PROGRESS,
    )

    try:
        data = json.loads(request.body)
        canvas_png_b64 = data.get("canvas_png")
        canvas_state = data.get("canvas_state", {})

        # Save final canvas state
        session.canvas_state = canvas_state
        if canvas_png_b64:
            if "," in canvas_png_b64:
                canvas_png_b64 = canvas_png_b64.split(",")[1]
            session.canvas_snapshot_png = base64.b64decode(canvas_png_b64)

        session.status = SystemDesignSession.Status.SUBMITTED
        session.submitted_at = timezone.now()
        session.save()

        # Run final analysis
        if session.canvas_snapshot_png:
            analyzer = get_diagram_analyzer()
            analyzer.analyze_canvas(
                session=session,
                png_data=session.canvas_snapshot_png,
                canvas_json=canvas_state,
                analysis_type=DiagramAnalysis.AnalysisType.FINAL,
            )

        # Generate scores
        scorer = get_scoring_service()
        score = scorer.score_session(session)

        return JsonResponse({
            "status": "success",
            "redirect_url": reverse("systemdesign:results", kwargs={"pk": session.pk}),
            "overall_score": score.overall_score,
        })

    except Exception as e:
        logger.exception("Failed to submit design: %s", str(e))
        # Revert status
        session.status = SystemDesignSession.Status.IN_PROGRESS
        session.submitted_at = None
        session.save()
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def abandon_session(request: HttpRequest, pk: int) -> HttpResponse:
    """Abandon a session without scoring."""
    session = get_object_or_404(
        SystemDesignSession,
        pk=pk,
        user=request.user,
        status=SystemDesignSession.Status.IN_PROGRESS,
    )

    session.end_session(SystemDesignSession.Status.ABANDONED)

    return redirect("systemdesign:config")


class SystemDesignResultsView(LoginRequiredMixin, DetailView):
    """View for displaying final results and scores."""

    model = SystemDesignSession
    template_name = "systemdesign/results.html"
    context_object_name = "session"

    def get_queryset(self):
        return SystemDesignSession.objects.filter(
            user=self.request.user,
            status__in=[
                SystemDesignSession.Status.COMPLETED,
                SystemDesignSession.Status.TIMED_OUT,
            ],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.object

        # Get score
        try:
            context["score"] = session.final_score
        except SystemDesignScore.DoesNotExist:
            context["score"] = None

        # Get final analysis
        context["final_analysis"] = session.analyses.filter(
            analysis_type=DiagramAnalysis.AnalysisType.FINAL
        ).first()

        # Get all messages
        context["messages"] = session.messages.order_by("created_at")

        # Challenge info
        context["challenge_title"] = session.effective_challenge_title
        context["description"] = session.effective_description

        # Time info
        if session.completed_at and session.started_at:
            elapsed = (session.completed_at - session.started_at).total_seconds()
            context["time_used"] = int(elapsed)
            context["time_used_formatted"] = f"{int(elapsed // 60)}:{int(elapsed % 60):02d}"
        else:
            context["time_used"] = session.time_limit_seconds
            context["time_used_formatted"] = f"{session.time_limit_seconds // 60}:00"

        return context
