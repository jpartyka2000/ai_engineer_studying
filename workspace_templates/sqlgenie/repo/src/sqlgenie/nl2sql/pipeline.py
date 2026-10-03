"""Question to answer, with every step audited.

The order is the point: **generate, scope, execute** -- and audit on every exit, not just
the one where everything worked. A refusal is the most interesting event this service
produces and it must leave a record, which is why the ``except`` arms here write audit
entries rather than simply raising.

Nothing in this module decides what is safe. It sequences steps whose safety is each
other module's job, and it makes sure that whichever of them says no, the fact that
somebody asked is written down.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlgenie.llm.recorded_client import CassetteMissError, RecordedClient
from sqlgenie.nl2sql import audit, generator
from sqlgenie.nl2sql.audit import AuditRecord, Outcome
from sqlgenie.nl2sql.executor import ExecutionError, ExecutionResult, execute
from sqlgenie.nl2sql.policy.row_level_policy import PolicyError, ScopedQuery, enforce_tenant_scope

logger = logging.getLogger(__name__)


def _jsonable(value: Any) -> Any:
    """Coerce one database value into something ``json.dumps`` accepts.

    Timestamps become ISO-8601 strings and arbitrary-precision numerics become strings
    rather than floats -- these are money columns, and turning an exact decimal into a
    float to make it serialise is how a total stops adding up.

    Args:
        value: A value from a result row.

    Returns:
        A JSON-native equivalent.
    """
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


class RefusedError(Exception):
    """Raised when a question was understood but will not be run.

    Distinct from :class:`~sqlgenie.nl2sql.executor.ExecutionError` so the API can map
    "we will not do this" to 400 and "we tried and it broke" to 500. Collapsing the two
    makes an attack look like an outage.
    """


@dataclass(frozen=True)
class Answer:
    """A answered question.

    Attributes:
        question: As asked.
        generated_sql: What the model produced.
        executed_sql: What ran, after rewriting.
        result: The rows.
        scoped: The policy's report on the rewrite.
    """

    question: str
    generated_sql: str
    executed_sql: str
    result: ExecutionResult
    scoped: ScopedQuery

    def as_dict(self) -> dict[str, Any]:
        """Return the answer as a JSON-serialisable dict.

        Row values are coerced here rather than left to the caller's encoder. A query
        over this schema routinely returns timestamps and numerics, neither of which
        the standard library will serialise, and "JSON-serialisable" is a promise this
        method either keeps or should stop making.
        """
        return {
            "question": self.question,
            "sql": self.executed_sql,
            "columns": list(self.result.columns),
            "rows": [{key: _jsonable(value) for key, value in row.items()} for row in self.result.rows],
            "row_count": self.result.row_count,
            "truncated": self.result.truncated,
            "tables": sorted(self.scoped.base_tables),
            "predicates_added": self.scoped.predicates_added,
        }


def ask(
    question: str,
    *,
    connection: Any,
    client: RecordedClient,
    tenant_id: str,
    max_rows: int,
    statement_timeout_ms: int,
) -> Answer:
    """Answer one question for one tenant.

    Args:
        question: The natural-language question.
        connection: An open psycopg connection inside a transaction.
        client: The recorded model client.
        tenant_id: The tenant to scope to.
        max_rows: Row ceiling.
        statement_timeout_ms: Per-statement timeout.

    Returns:
        An :class:`Answer`.

    Raises:
        RefusedError: If the question has no recording, or the policy will not scope the
            generated SQL.
        ExecutionError: If the scoped statement failed to run.
    """
    try:
        generation = generator.generate_sql(client, question)
    except CassetteMissError as exc:
        audit.record(
            AuditRecord(
                tenant_id=tenant_id,
                question=question,
                generated_sql="",
                executed_sql=None,
                outcome=Outcome.REFUSED,
                reason=f"no recorded generation: {exc}",
            )
        )
        raise RefusedError("no recorded generation for this question") from exc

    try:
        scoped = enforce_tenant_scope(generation.sql)
    except PolicyError as exc:
        # The rejection path, audited with the SQL that was refused. This is the branch
        # an investigator reads first after an incident, and it is the one most often
        # missing from services like this.
        audit.record(
            AuditRecord(
                tenant_id=tenant_id,
                question=question,
                generated_sql=generation.sql,
                executed_sql=None,
                outcome=Outcome.REFUSED,
                reason=str(exc),
            )
        )
        raise RefusedError(str(exc)) from exc

    try:
        result = execute(
            connection,
            scoped,
            tenant_id=tenant_id,
            max_rows=max_rows,
            statement_timeout_ms=statement_timeout_ms,
        )
    except ExecutionError as exc:
        audit.record(
            AuditRecord(
                tenant_id=tenant_id,
                question=question,
                generated_sql=generation.sql,
                executed_sql=scoped.sql,
                outcome=Outcome.FAILED,
                base_tables=tuple(sorted(scoped.base_tables)),
                predicates_added=scoped.predicates_added,
                reason=str(exc),
            )
        )
        raise

    audit.record(
        AuditRecord(
            tenant_id=tenant_id,
            question=question,
            generated_sql=generation.sql,
            executed_sql=scoped.sql,
            outcome=Outcome.EXECUTED,
            base_tables=tuple(sorted(scoped.base_tables)),
            predicates_added=scoped.predicates_added,
            row_count=result.row_count,
        )
    )
    return Answer(
        question=question,
        generated_sql=generation.sql,
        executed_sql=scoped.sql,
        result=result,
        scoped=scoped,
    )
