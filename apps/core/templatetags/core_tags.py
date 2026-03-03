"""Custom template tags and filters for the core app."""

from django import template

register = template.Library()


@register.filter
def index_to_letter(value):
    """Convert a 0-based index to a letter (0->A, 1->B, etc.)."""
    try:
        return chr(65 + int(value))
    except (ValueError, TypeError):
        return ""


@register.filter
def format_ms(value):
    """Format milliseconds to a human-readable string."""
    try:
        ms = int(value)
        if ms < 1000:
            return f"{ms}ms"
        elif ms < 60000:
            return f"{ms / 1000:.1f}s"
        else:
            minutes = ms // 60000
            seconds = (ms % 60000) // 1000
            return f"{minutes}m {seconds}s"
    except (ValueError, TypeError):
        return str(value)
