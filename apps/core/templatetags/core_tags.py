"""Custom template tags and filters for the core app."""

import re

from django.utils.html import escape
from django.utils.safestring import mark_safe
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


@register.filter(is_safe=True)
def render_code_blocks(value):
    """
    Convert markdown code blocks to HTML with syntax highlighting support.

    Handles both fenced code blocks (```python...```) and inline code (`code`).
    """
    if not value:
        return ""

    text = str(value)

    # Pattern for fenced code blocks: ```language\ncode\n```
    fenced_pattern = r"```(\w*)\n(.*?)```"

    def replace_fenced(match):
        language = match.group(1) or "plaintext"
        code = match.group(2).rstrip()
        escaped_code = escape(code)
        return (
            f'<pre class="code-block"><code class="language-{language}">'
            f"{escaped_code}</code></pre>"
        )

    # Replace fenced code blocks (use DOTALL to match across newlines)
    text = re.sub(fenced_pattern, replace_fenced, text, flags=re.DOTALL)

    # Pattern for inline code: `code`
    inline_pattern = r"`([^`]+)`"
    text = re.sub(
        inline_pattern,
        r'<code class="inline-code">\1</code>',
        text,
    )

    # Convert remaining newlines to <br> tags (but not inside pre tags)
    # Split by pre tags, process non-pre parts
    parts = re.split(r"(<pre.*?</pre>)", text, flags=re.DOTALL)
    result = []
    for part in parts:
        if part.startswith("<pre"):
            result.append(part)
        else:
            # Convert newlines to <br> for non-code parts
            result.append(part.replace("\n", "<br>\n"))

    return mark_safe("".join(result))
