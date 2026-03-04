"""
Q&A mode models.

This module contains models for the Q&A (Question & Answer) study mode,
where users can have conversational exchanges with Claude about a subject.
"""

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class QASession(models.Model):
    """
    Represents a Q&A conversation session with Claude.

    Users can have multiple Q&A sessions per subject. Sessions are long-lived
    and can be resumed. Each session maintains conversation history and tracks
    statistics like message count and token usage.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        ARCHIVED = "archived", _("Archived")

    # Relationships
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="qa_sessions",
        help_text=_("The user who owns this session"),
    )
    subject = models.ForeignKey(
        "subjects.Subject",
        on_delete=models.CASCADE,
        related_name="qa_sessions",
        help_text=_("The subject area for this conversation"),
    )

    # Metadata
    title = models.CharField(
        max_length=200,
        blank=True,
        help_text=_("Auto-generated or user-provided session title"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
        help_text=_("Session status"),
    )

    # Statistics
    message_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Total number of messages in this session"),
    )
    total_tokens_estimate = models.PositiveIntegerField(
        default=0,
        help_text=_("Estimated total tokens used (4 chars = 1 token)"),
    )

    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Timestamp of most recent message"),
    )

    class Meta:
        ordering = ["-last_message_at"]
        verbose_name = _("Q&A Session")
        verbose_name_plural = _("Q&A Sessions")
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["subject", "status"]),
        ]

    def __str__(self) -> str:
        title = self.title or f"{self.subject.name} Discussion"
        return f"{self.user.username} - {title} ({self.started_at:%Y-%m-%d})"

    def get_absolute_url(self) -> str:
        """Get the URL for this session."""
        return reverse(
            "qanda:session",
            kwargs={"subject_slug": self.subject.slug, "pk": self.pk},
        )

    def get_system_message(self) -> str:
        """
        Generate system message for Claude based on subject.

        Returns:
            str: The system message to prime Claude's responses.
        """
        return (
            f"You are an expert instructor specializing in {self.subject.name}. "
            f"Your role is to help the user learn through clear explanations, "
            f"practical examples, and best practices. "
            f"Format your responses using markdown. "
            f"When providing code examples, include language tags for syntax highlighting. "
            f"Be pedagogical, thorough, and cite authoritative sources when applicable."
        )

    def get_system_message_with_context(self, max_doc_tokens: int = 8000) -> str:
        """
        Generate system message including relevant study materials as context.

        Includes stored documents for the subject to provide Claude with
        reference material when answering questions.

        Args:
            max_doc_tokens: Maximum tokens to use for document context.

        Returns:
            str: System message with embedded document context.
        """
        base = self.get_system_message()

        # Get study materials for this subject
        materials = self.subject.study_materials.filter(is_active=True).order_by(
            "-created_at"
        )

        if not materials.exists():
            return base

        # Build context from materials, respecting token limit
        context = "\n\n## Reference Materials\n"
        context += "Use the following study materials to inform your responses:\n"
        tokens_used = 0

        for material in materials:
            if tokens_used + material.token_estimate > max_doc_tokens:
                break
            context += f"\n### {material.title}\n{material.content}\n"
            tokens_used += material.token_estimate

        return base + context

    def get_conversation_history(self, max_tokens: int = 100000) -> list[dict]:
        """
        Get conversation history for Claude API, truncated to fit token limit.

        This method builds the conversation history from most recent messages
        backwards until the token limit is reached. This ensures the API context
        window is respected while maintaining recent conversation context.

        Args:
            max_tokens: Maximum tokens to include in history (default: 100,000).

        Returns:
            list[dict]: List of message dicts in Claude API format:
                [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
        """
        messages = self.messages.order_by("created_at")

        # Build from most recent backwards until we hit token limit
        history = []
        token_count = 0

        for msg in reversed(messages):
            if token_count + msg.token_count_estimate > max_tokens:
                break
            history.insert(
                0,
                {
                    "role": msg.role,
                    "content": msg.content,
                },
            )
            token_count += msg.token_count_estimate

        return history

    def generate_title(self) -> str:
        """
        Auto-generate a title from first user message.

        Returns:
            str: Generated title (first 50 chars of first user message or default).
        """
        first_user_msg = self.messages.filter(role=Message.Role.USER).first()
        if first_user_msg:
            # Take first 50 chars of first message
            content = first_user_msg.content.strip()
            if len(content) > 50:
                return content[:50] + "..."
            return content
        return f"{self.subject.name} Discussion"

    def update_statistics(self) -> None:
        """Update message count and token estimate from related messages."""
        messages = self.messages.all()
        self.message_count = messages.count()
        self.total_tokens_estimate = sum(msg.token_count_estimate for msg in messages)
        self.last_message_at = timezone.now()
        self.save(
            update_fields=["message_count", "total_tokens_estimate", "last_message_at"]
        )


class Message(models.Model):
    """
    Represents a single message in a Q&A conversation.

    Messages can be from 'user' or 'assistant' (Claude). Each message tracks
    its content, token count estimate, and any metadata about quick actions.
    """

    class Role(models.TextChoices):
        USER = "user", _("User")
        ASSISTANT = "assistant", _("Assistant")

    # Relationships
    session = models.ForeignKey(
        QASession,
        on_delete=models.CASCADE,
        related_name="messages",
        help_text=_("The session this message belongs to"),
    )

    # Content
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        help_text=_("Who sent this message"),
    )
    content = models.TextField(
        help_text=_("Message content (markdown supported)"),
    )

    # Metadata
    token_count_estimate = models.PositiveIntegerField(
        default=0,
        help_text=_("Estimated token count (4 chars ≈ 1 token)"),
    )
    quick_action = models.CharField(
        max_length=50,
        blank=True,
        help_text=_("If generated by quick action button (e.g., 'explain_further')"),
    )
    reference_message_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("ID of message this is in reference to (for quick actions)"),
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("Message")
        verbose_name_plural = _("Messages")
        indexes = [
            models.Index(fields=["session", "created_at"]),
        ]

    def __str__(self) -> str:
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"{self.get_role_display()}: {preview}"

    def save(self, *args, **kwargs) -> None:
        """Estimate token count on save if not already set."""
        if not self.token_count_estimate:
            # Rough estimate: 4 characters ≈ 1 token
            self.token_count_estimate = len(self.content) // 4
        super().save(*args, **kwargs)
