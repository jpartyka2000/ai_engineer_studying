"""Prompt assembly.

**Every byte of this file is part of a cache key.** The rendered prompt is hashed to
look up a recorded generation, so a reworded instruction, a reordered section or a
stray trailing space invalidates the entire cassette set. Assembly is therefore pure and
deterministic: no timestamps, no dict iteration order, no "helpfully" interpolated
context that varies per request.

**The prompt is not a security control.** It asks for tenant-scoped SQL, and asking is
all it does. A model that ignores the instruction, or a question crafted to talk it out
of the instruction, produces SQL that is then constrained by
:mod:`sqlgenie.nl2sql.policy.row_level_policy` -- which is where the boundary actually
is. The instruction is here because scoped SQL is easier to rewrite correctly than
unscoped SQL, not because it protects anything.
"""

from __future__ import annotations

from sqlgenie.nl2sql import catalog

#: The system prompt. Stable text, versioned by the cassette keys that depend on it.
SYSTEM_PROMPT = """\
You are a careful analytics engineer. You translate a business question into exactly one
PostgreSQL SELECT statement.

Rules:
- Return SQL only. No prose, no markdown fences, no trailing semicolon.
- Exactly one statement. Never use INSERT, UPDATE, DELETE, DDL or multiple statements.
- Use only the tables given in the schema. Never reference system catalogs.
- Prefer explicit JOIN syntax and qualify columns with a table alias.
- Money is stored as integer cents in *_cents columns. Never divide it in SQL.
"""

#: Guidance added for questions that compare two periods or two cohorts. Introduced
#: because flat subquery-per-metric SQL was producing wrong answers on year-over-year
#: questions; it is also what made common table expressions common in generated output.
COMPARATIVE_GUIDANCE = """\
For questions that compare periods or cohorts, build each side as a named common table
expression and join them in the final SELECT. This keeps each side's filters explicit
and avoids repeating an aggregate in two places.
"""

#: Question words that trigger :data:`COMPARATIVE_GUIDANCE`. Matched case-insensitively
#: against the whole question. Deliberately a fixed, sorted tuple: the set of triggers is
#: part of what determines the prompt text, and therefore part of the cassette key.
COMPARATIVE_TRIGGERS: tuple[str, ...] = (
    "compared to",
    "compare",
    "last year",
    "month over month",
    "previous period",
    "versus",
    "vs",
    "year over year",
)


def is_comparative(question: str) -> bool:
    """Return whether a question asks for a comparison.

    Args:
        question: The natural-language question.

    Returns:
        Whether any trigger phrase appears.
    """
    lowered = question.lower()
    return any(trigger in lowered for trigger in COMPARATIVE_TRIGGERS)


def build_prompt(question: str) -> str:
    """Render the user prompt for a question.

    Args:
        question: The natural-language question.

    Returns:
        The prompt text, byte-for-byte reproducible for a given question and catalog.
    """
    sections = [
        "Schema:",
        catalog.schema_prompt_section(),
        "",
    ]
    if is_comparative(question):
        sections.extend([COMPARATIVE_GUIDANCE.strip(), ""])
    sections.extend([f"Question: {question.strip()}", "", "SQL:"])
    return "\n".join(sections)
