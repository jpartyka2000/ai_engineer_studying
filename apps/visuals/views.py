"""Views for the visuals app."""

import json
import logging

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, TemplateView

from apps.core.services.claude_service import ClaudeAPIError, get_claude_service
from apps.subjects.models import Subject

from .models import VisualSession, VisualTopic

logger = logging.getLogger(__name__)


class VisualTopicListView(LoginRequiredMixin, TemplateView):
    """List available visual topics for a subject."""

    template_name = "visuals/topic_list.html"

    def get_context_data(self, **kwargs):
        """Add subject and topics to context."""
        context = super().get_context_data(**kwargs)
        subject = get_object_or_404(
            Subject,
            slug=kwargs["subject_slug"],
            is_active=True,
            supports_visuals=True,
        )
        context["subject"] = subject

        # Get published topics for this subject
        topics = VisualTopic.objects.filter(
            subject=subject,
            status=VisualTopic.Status.PUBLISHED,
        ).order_by("title")

        # Get user's progress for each topic
        user_sessions = {
            vs.visual_topic_id: vs
            for vs in VisualSession.objects.filter(
                user=self.request.user,
                visual_topic__in=topics,
            )
        }

        # Annotate topics with user progress
        topics_with_progress = []
        for topic in topics:
            session = user_sessions.get(topic.id)
            topics_with_progress.append(
                {
                    "topic": topic,
                    "session": session,
                    "progress": session.progress_percentage if session else 0,
                    "completed": session.completed if session else False,
                }
            )

        context["topics"] = topics_with_progress
        return context


class VisualViewerView(LoginRequiredMixin, DetailView):
    """Main visual viewer with step navigation."""

    model = VisualTopic
    template_name = "visuals/viewer.html"
    context_object_name = "topic"
    slug_url_kwarg = "topic_slug"

    def get_queryset(self):
        """Filter by subject and published status."""
        return VisualTopic.objects.filter(
            subject__slug=self.kwargs["subject_slug"],
            status=VisualTopic.Status.PUBLISHED,
        ).select_related("subject")

    def get_context_data(self, **kwargs):
        """Add steps data and user session to context."""
        context = super().get_context_data(**kwargs)

        # Get or create user session
        session, created = VisualSession.objects.get_or_create(
            user=self.request.user,
            visual_topic=self.object,
        )
        context["session"] = session

        # Prepare steps data for JavaScript
        context["steps_json"] = json.dumps(self.object.steps)
        context["total_steps"] = len(self.object.steps)
        context["initial_step"] = session.current_step

        return context


@login_required
@require_POST
def update_progress(request, subject_slug, topic_slug):
    """
    Update user's progress when they view a step.

    Called via JavaScript when user navigates to a new step.
    """
    topic = get_object_or_404(
        VisualTopic,
        subject__slug=subject_slug,
        slug=topic_slug,
        status=VisualTopic.Status.PUBLISHED,
    )

    # Get step number from request
    try:
        step_number = int(request.POST.get("step", 0))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid step number"}, status=400)

    # Validate step number
    if step_number < 0 or step_number >= len(topic.steps):
        return JsonResponse({"error": "Step out of range"}, status=400)

    # Get or create session and update progress
    session, _ = VisualSession.objects.get_or_create(
        user=request.user,
        visual_topic=topic,
    )
    session.update_progress(step_number)

    return JsonResponse(
        {
            "status": "success",
            "current_step": session.current_step,
            "max_step_reached": session.max_step_reached,
            "completed": session.completed,
            "progress_percentage": session.progress_percentage,
        }
    )


@login_required
@require_POST
def explain_step(request, subject_slug, topic_slug, step_number):
    """
    Request Claude explanation for a step.

    Returns stream URL for frontend to connect to SSE.
    """
    topic = get_object_or_404(
        VisualTopic,
        subject__slug=subject_slug,
        slug=topic_slug,
        status=VisualTopic.Status.PUBLISHED,
    )

    # Validate step number
    if step_number < 0 or step_number >= len(topic.steps):
        return JsonResponse({"error": "Invalid step number"}, status=400)

    # Build stream URL
    stream_url = f"/visuals/{subject_slug}/{topic_slug}/explain/{step_number}/stream/"

    return JsonResponse(
        {
            "status": "success",
            "stream_url": stream_url,
        }
    )


@login_required
def stream_explanation(request, subject_slug, topic_slug, step_number):
    """
    Stream Claude's explanation using Server-Sent Events (SSE).

    This view establishes an SSE connection and streams the explanation
    in real-time as it's generated by Claude.
    """
    topic = get_object_or_404(
        VisualTopic,
        subject__slug=subject_slug,
        slug=topic_slug,
        status=VisualTopic.Status.PUBLISHED,
    )

    # Validate step number
    if step_number < 0 or step_number >= len(topic.steps):
        return JsonResponse({"error": "Invalid step number"}, status=400)

    step = topic.steps[step_number]

    def build_explanation_prompt(topic: VisualTopic, step: dict) -> str:
        """Build the prompt for Claude to explain this step."""
        diagram_info = step.get("diagram_data", "")
        if isinstance(diagram_info, dict):
            diagram_info = json.dumps(diagram_info, indent=2)

        return f"""The user is viewing step {step.get("step_number", step_number) + 1} of "{topic.title}".

**Step Title:** {step.get("title", "Untitled Step")}

**Current Explanation:** {step.get("explanation", "")}

**Diagram Content:**
```
{diagram_info}
```

Please provide a more detailed explanation of this step:
1. Explain the concept shown in simple, clear terms
2. Provide relevant code examples if applicable to {topic.subject.name}
3. Mention common pitfalls or misconceptions related to this step
4. Connect this concept to practical, real-world applications

Keep your explanation focused, educational, and complementary to the visual diagram."""

    def event_stream():
        """Generator for SSE events."""
        try:
            claude_service = get_claude_service()
            full_content = []

            # Stream from Claude
            for chunk in claude_service.stream_completion(
                prompt=build_explanation_prompt(topic, step),
                system_message=topic.get_system_message(),
                max_tokens=2048,
                temperature=0.7,
            ):
                full_content.append(chunk)
                # SSE format: "data: {json}\n\n"
                data = json.dumps({"chunk": chunk})
                yield f"data: {data}\n\n"

            # Send completion event
            data = json.dumps({"done": True})
            yield f"data: {data}\n\n"

        except ClaudeAPIError as e:
            logger.exception(f"Claude API error during streaming: {e}")
            error_data = json.dumps(
                {"error": "Failed to generate explanation. Please try again."}
            )
            yield f"data: {error_data}\n\n"
        except Exception as e:
            logger.exception(f"Unexpected error during streaming: {e}")
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
