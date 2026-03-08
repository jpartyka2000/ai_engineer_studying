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
    Convert markdown to HTML with syntax highlighting support.

    Handles:
    - Fenced code blocks (```python...```)
    - Inline code (`code`)
    - Bold text (**bold**)
    - Bullet points (- item)
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

    # Pattern for bold text: **bold**
    bold_pattern = r"\*\*([^*]+)\*\*"
    text = re.sub(bold_pattern, r"<strong>\1</strong>", text)

    # Pattern for section headers: "Title:" at start of line (not already bold)
    # Match lines that are just a title with colon, or title: followed by newline
    header_pattern = r"(^|\n)([A-Z][^:\n]{2,50}:)\s*(?=\n|$)"
    text = re.sub(
        header_pattern,
        r'\1<span class="font-semibold text-base text-gray-800 border-b border-gray-300 pb-1 inline-block mb-1">\2</span>',
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
            # Convert bullet points: "- item" at start of line
            part = re.sub(
                r"(^|\n)- ",
                r'\1<span class="ml-4">•</span> ',
                part,
            )
            # Convert newlines to <br> for non-code parts
            part = part.replace("\n", "<br>\n")
            result.append(part)

    return mark_safe("".join(result))
