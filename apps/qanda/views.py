"""Views for the qanda (Q&A) app."""

import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import models
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, TemplateView

from apps.core.services.claude_service import ClaudeAPIError, get_claude_service
from apps.subjects.models import Subject

from .models import Message, QASession

logger = logging.getLogger(__name__)


class QAHomeView(LoginRequiredMixin, TemplateView):
    """List existing Q&A sessions for a subject or start a new one."""

    template_name = "qanda/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subject = get_object_or_404(
            Subject, slug=kwargs["subject_slug"], is_active=True
        )
        context["subject"] = subject

        # Get active sessions for this user and subject
        active_sessions = QASession.objects.filter(
            user=self.request.user,
            subject=subject,
            status=QASession.Status.ACTIVE,
        ).select_related("subject")

        # Get archived sessions
        archived_sessions = QASession.objects.filter(
            user=self.request.user,
            subject=subject,
            status=QASession.Status.ARCHIVED,
        ).select_related("subject")

        context["sessions"] = active_sessions
        context["archived_sessions"] = archived_sessions
        return context


@login_required
@require_POST
def start_qa_session(request, subject_slug):
    """Start a new Q&A session."""
    subject = get_object_or_404(Subject, slug=subject_slug, is_active=True)

    # Create new session
    session = QASession.objects.create(
        user=request.user,
        subject=subject,
        title="",  # Will be auto-generated from first message
    )

    messages.success(request, _("Q&A session started! Ask your first question."))
    return redirect("qanda:session", subject_slug=subject.slug, pk=session.pk)


class QASessionView(LoginRequiredMixin, DetailView):
    """Main chat interface for Q&A session."""

    model = QASession
    template_name = "qanda/session.html"
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
        context["chat_messages"] = self.object.messages.all()
        context["is_archived"] = self.object.status == QASession.Status.ARCHIVED
        return context


@login_required
@require_POST
def ask_question(request, subject_slug, pk):
    """
    Handle user question submission.

    Creates user message and placeholder assistant message,
    then returns stream URL for frontend to connect to.
    """
    session = get_object_or_404(
        QASession,
        pk=pk,
        user=request.user,
    )

    # Don't allow questions on archived sessions
    if session.status == QASession.Status.ARCHIVED:
        return JsonResponse(
            {"error": "Cannot ask questions in archived sessions. Please unarchive first."},
            status=403
        )

    # Get question from request
    question = request.POST.get("question", "").strip()
    quick_action = request.POST.get("quick_action", "").strip()
    reference_message_id = request.POST.get("reference_message_id", "")

    if not question:
        return JsonResponse({"error": "Question is required"}, status=400)

    # Validate question length (max 10k characters)
    if len(question) > 10000:
        return JsonResponse(
            {"error": "Question is too long (max 10,000 characters)"}, status=400
        )

    # Create user message
    user_message = Message.objects.create(
        session=session,
        role=Message.Role.USER,
        content=question,
        quick_action=quick_action,
        reference_message_id=int(reference_message_id)
        if reference_message_id
        else None,
    )

    # Create placeholder assistant message (content will be filled during streaming)
    assistant_message = Message.objects.create(
        session=session,
        role=Message.Role.ASSISTANT,
        content="",  # Will be filled by streaming
    )

    # Update session metadata
    session.last_message_at = timezone.now()
    session.save(update_fields=["last_message_at"])

    # Auto-generate title from first user message if needed
    if not session.title and session.message_count == 0:
        session.title = session.generate_title()
        session.save(update_fields=["title"])

    # Build stream URL
    stream_url = f"/qanda/{subject_slug}/{pk}/stream/{assistant_message.id}/"

    return JsonResponse(
        {
            "status": "success",
            "message_id": assistant_message.id,
            "stream_url": stream_url,
            "user_message_id": user_message.id,
        }
    )


@login_required
def stream_response(request, subject_slug, pk, message_id):
    """
    Stream Claude's response using Server-Sent Events (SSE).

    This view establishes an SSE connection and streams the response
    in real-time as it's generated by Claude.
    """
    # Get session and verify ownership
    session = get_object_or_404(
        QASession,
        pk=pk,
        user=request.user,
    )

    # Don't allow streaming for archived sessions
    if session.status == QASession.Status.ARCHIVED:
        return JsonResponse({"error": "Cannot stream responses for archived sessions"}, status=403)

    # Get the assistant message to fill
    message = get_object_or_404(
        Message,
        pk=message_id,
        session=session,
        role=Message.Role.ASSISTANT,
    )

    # Get most recent user message
    last_user_msg = (
        session.messages.filter(role=Message.Role.USER).order_by("-created_at").first()
    )

    if not last_user_msg:
        return JsonResponse({"error": "No user message found"}, status=400)

    # Get conversation history (excluding current empty assistant message and last user message)
    # We exclude the last user message because it will be sent as the prompt
    history = []
    for msg in session.messages.order_by("created_at"):
        # Skip the current placeholder assistant message and the last user message
        if msg.id == message.id or msg.id == last_user_msg.id:
            continue
        # Skip any messages with empty content
        if not msg.content.strip():
            continue
        history.append({
            "role": msg.role,
            "content": msg.content,
        })

    def event_stream():
        """Generator for SSE events."""
        try:
            claude_service = get_claude_service()
            full_content = []

            # Stream from Claude
            for chunk in claude_service.stream_completion(
                prompt=last_user_msg.content,
                system_message=session.get_system_message(),
                conversation_history=history,
                max_tokens=4096,
                temperature=0.7,
            ):
                full_content.append(chunk)
                # SSE format: "data: {json}\n\n"
                data = json.dumps({"chunk": chunk})
                yield f"data: {data}\n\n"

            # Save complete message
            message.content = "".join(full_content)
            message.token_count_estimate = len(message.content) // 4
            message.save()

            # Update session statistics
            session.update_statistics()

            # Send completion event
            data = json.dumps({"done": True, "message_id": message.id})
            yield f"data: {data}\n\n"

        except ClaudeAPIError as e:
            logger.exception(f"Claude API error during streaming: {e}")
            error_data = json.dumps(
                {"error": "Failed to generate response. Please try again."}
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


@login_required
def export_session(request, subject_slug, pk):
    """Export conversation as markdown file."""
    session = get_object_or_404(
        QASession,
        pk=pk,
        user=request.user,
    )

    # Generate markdown content
    lines = []
    lines.append(f"# Q&A Session: {session.subject.name}")
    lines.append(f"**Date**: {session.started_at.strftime('%Y-%m-%d %H:%M')}")
    if session.title:
        lines.append(f"**Title**: {session.title}")
    lines.append(f"**Messages**: {session.message_count}")
    lines.append("\n---\n")

    # Add all messages
    for i, msg in enumerate(session.messages.all(), 1):
        role = "User" if msg.role == Message.Role.USER else "Assistant"
        lines.append(f"## Message {i} - {role}")
        lines.append(f"*{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}*\n")
        lines.append(msg.content)
        lines.append("\n")

    markdown_content = "\n".join(lines)

    # Create filename
    filename = f"qanda_{session.subject.slug}_{session.started_at.strftime('%Y%m%d_%H%M')}.md"

    # Return as downloadable file
    response = HttpResponse(markdown_content, content_type="text/markdown")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_POST
def archive_session(request, subject_slug, pk):
    """Archive a Q&A session."""
    session = get_object_or_404(
        QASession,
        pk=pk,
        user=request.user,
    )

    session.status = QASession.Status.ARCHIVED
    session.save(update_fields=["status"])

    messages.success(request, _("Session archived successfully."))
    return redirect("qanda:home", subject_slug=subject_slug)


@login_required
@require_POST
def unarchive_session(request, subject_slug, pk):
    """Unarchive a Q&A session."""
    session = get_object_or_404(
        QASession,
        pk=pk,
        user=request.user,
    )

    session.status = QASession.Status.ACTIVE
    session.save(update_fields=["status"])

    messages.success(request, _("Session restored successfully."))
    return redirect("qanda:session", subject_slug=subject_slug, pk=pk)
