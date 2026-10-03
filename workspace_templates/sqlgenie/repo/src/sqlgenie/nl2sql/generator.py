"""Question in, SQL out.

Thin on purpose. Everything that decides whether the SQL is *safe* lives downstream in
:mod:`sqlgenie.nl2sql.policy.row_level_policy`, and everything that decides whether it is
*answerable* lives in :mod:`sqlgenie.nl2sql.catalog`. This module only assembles a
request and hands back what came out, so that "what did the model say" and "what are we
willing to run" never get entangled.
"""

from __future__ import annotations

import logging
import re

from sqlgenie.llm.recorded_client import Generation, RecordedClient
from sqlgenie.nl2sql import prompt as prompt_module

logger = logging.getLogger(__name__)

#: Fences a model wraps SQL in when it ignores the "SQL only" instruction. Stripped
#: because the alternative is a parse error on an otherwise perfectly good statement.
_FENCE = re.compile(r"^\s*```(?:sql)?\s*(?P<body>.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


def clean_sql(raw: str) -> str:
    """Strip fences and a trailing semicolon from a generated statement.

    A trailing semicolon is removed rather than tolerated because it turns a single
    statement into a statement plus an empty one, and the policy refuses anything that
    parses as more than one statement.

    Args:
        raw: The model's raw output.

    Returns:
        Bare SQL.
    """
    match = _FENCE.match(raw)
    text = match.group("body") if match else raw
    return text.strip().rstrip(";").strip()


def generate_sql(client: RecordedClient, question: str) -> Generation:
    """Generate SQL for a question.

    Args:
        client: The recorded client.
        question: The natural-language question.

    Returns:
        A :class:`~sqlgenie.llm.recorded_client.Generation` whose ``sql`` has been
        cleaned but **not** validated, scoped or executed.

    Raises:
        sqlgenie.llm.recorded_client.CassetteMissError: If nothing is recorded.
    """
    rendered = prompt_module.build_prompt(question)
    generation = client.generate(system=prompt_module.SYSTEM_PROMPT, prompt=rendered)
    cleaned = clean_sql(generation.sql)
    logger.debug("generated %d chars of SQL for %r", len(cleaned), question[:60])
    return Generation(
        sql=cleaned,
        key=generation.key,
        question=question,
        notes=generation.notes,
    )
