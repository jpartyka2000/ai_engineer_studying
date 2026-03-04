"""Admin configuration for the qanda app."""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Message, QASession


class MessageInline(admin.TabularInline):
    """Inline admin for Message within QASession."""

    model = Message
    extra = 0
    readonly_fields = [
        "role",
        "content_preview",
        "token_count_estimate",
        "quick_action",
        "created_at",
    ]
    fields = [
        "role",
        "content_preview",
        "token_count_estimate",
        "quick_action",
        "created_at",
    ]
    can_delete = False

    def content_preview(self, obj):
        """Display truncated message content."""
        text = obj.content[:100]
        if len(obj.content) > 100:
            text += "..."
        return text

    content_preview.short_description = _("Content")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(QASession)
class QASessionAdmin(admin.ModelAdmin):
    """Admin interface for QASession model."""

    list_display = [
        "user",
        "subject",
        "title_display",
        "message_count",
        "tokens_display",
        "status",
        "last_message_at",
    ]
    list_filter = ["status", "subject", "started_at"]
    search_fields = ["user__username", "subject__name", "title"]
    ordering = ["-last_message_at"]
    readonly_fields = [
        "started_at",
        "last_message_at",
        "message_count",
        "total_tokens_estimate",
    ]
    inlines = [MessageInline]

    fieldsets = [
        (
            None,
            {
                "fields": ["user", "subject", "title", "status"],
            },
        ),
        (
            _("Statistics"),
            {
                "fields": [
                    "message_count",
                    "total_tokens_estimate",
                ],
            },
        ),
        (
            _("Timestamps"),
            {
                "fields": ["started_at", "last_message_at"],
            },
        ),
    ]

    def title_display(self, obj):
        """Display title or generated title."""
        return obj.title or obj.generate_title()

    title_display.short_description = _("Title")

    def tokens_display(self, obj):
        """Display token count with formatting."""
        tokens = obj.total_tokens_estimate
        if tokens > 1000:
            return f"{tokens / 1000:.1f}k"
        return str(tokens)

    tokens_display.short_description = _("Tokens")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    """Admin interface for Message model."""

    list_display = [
        "session_link",
        "role",
        "content_preview",
        "token_count_estimate",
        "quick_action_display",
        "created_at",
    ]
    list_filter = ["role", "quick_action", "session__subject"]
    search_fields = ["content", "session__user__username", "session__title"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "token_count_estimate"]

    fieldsets = [
        (
            None,
            {
                "fields": ["session", "role", "content"],
            },
        ),
        (
            _("Metadata"),
            {
                "fields": [
                    "token_count_estimate",
                    "quick_action",
                    "reference_message_id",
                ],
            },
        ),
        (
            _("Timestamps"),
            {
                "fields": ["created_at"],
            },
        ),
    ]

    def session_link(self, obj):
        """Display clickable link to session."""
        url = obj.session.get_absolute_url()
        return format_html('<a href="{}">{}</a>', url, str(obj.session))

    session_link.short_description = _("Session")

    def content_preview(self, obj):
        """Display truncated message content."""
        text = obj.content[:100]
        if len(obj.content) > 100:
            text += "..."
        return text

    content_preview.short_description = _("Content")

    def quick_action_display(self, obj):
        """Display quick action if present."""
        if obj.quick_action:
            return obj.quick_action.replace("_", " ").title()
        return "-"

    quick_action_display.short_description = _("Quick Action")
