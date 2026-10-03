"""Running a scoped statement, under limits.

Three limits, all applied here rather than hoped for upstream.

**The tenant is bound, never interpolated.** The rewritten SQL carries
``%(tenant_id)s`` and the value travels as a query parameter. No part of this service
formats a tenant id into a string that becomes SQL, which is why there is no escaping
function anywhere in the codebase -- there is nothing to escape.

**A statement timeout**, set per transaction. Generated SQL is not reviewed by a human
before it runs, and a question like "every order joined to every other order" is one
sentence to ask and a long time to answer.

**A row ceiling**, enforced by asking for one row more than the ceiling and reporting
truncation when it arrives. Counting what came back and comparing is the obvious
alternative and it is wrong: by then the rows have already crossed the wire.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Sequence

from sqlgenie.nl2sql.policy.row_level_policy import ScopedQuery

logger = logging.getLogger(__name__)


class ExecutionError(Exception):
    """Raised when a scoped statement could not be run."""


@dataclass(frozen=True)
class ExecutionResult:
    """What came back.

    Attributes:
        columns: Column names, in result order.
        rows: The rows, at most ``max_rows`` of them.
        truncated: Whether more rows existed than were returned.
        row_count: Rows actually returned.
    """

    columns: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    truncated: bool
    row_count: int


def execute(
    connection: Any,
    scoped: ScopedQuery,
    *,
    tenant_id: str,
    max_rows: int,
    statement_timeout_ms: int,
) -> ExecutionResult:
    """Execute a scoped statement for one tenant.

    Args:
        connection: An open psycopg connection. Not opened here, because the caller
            owns the transaction boundary and this must run inside it.
        scoped: The rewritten query.
        tenant_id: Bound as the ``tenant_id`` parameter. Never formatted into the SQL.
        max_rows: Row ceiling.
        statement_timeout_ms: Per-statement timeout.

    Returns:
        An :class:`ExecutionResult`.

    Raises:
        ExecutionError: If the statement fails. The database's message is included
            because it is useful, and the SQL is not, because the caller already has it
            and the audit record already holds it.
    """
    if scoped.touches_tenant_data and scoped.predicates_added == 0:
        # Belt and braces. The policy already guarantees this; asserting it again at
        # the point of execution means a future refactor that loosens the policy cannot
        # quietly turn this into an unscoped read.
        raise ExecutionError(
            "refusing to execute a statement that reads tenant data with no tenant "
            "predicate applied"
        )

    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL statement_timeout = {int(statement_timeout_ms)}")
            # The row-level security policies read app.tenant_id. It is set with
            # set_config rather than `SET LOCAL app.tenant_id = ...` because SET does
            # not accept a bound parameter -- the value would have to be formatted into
            # the statement, which is precisely the thing this service never does.
            # The third argument makes it transaction-local, so it cannot outlive the
            # request and be inherited by whatever reuses this pooled connection.
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            cursor.execute(scoped.sql, {"tenant_id": tenant_id})
            fetched: Sequence[dict[str, Any]] = cursor.fetchmany(max_rows + 1)
            columns = tuple(desc.name for desc in (cursor.description or ()))
    except Exception as exc:  # noqa: BLE001 - psycopg raises a wide variety
        raise ExecutionError(str(exc).strip()) from exc

    truncated = len(fetched) > max_rows
    rows = tuple(fetched[:max_rows])
    logger.debug("executed for tenant=%s rows=%d truncated=%s", tenant_id, len(rows), truncated)
    return ExecutionResult(
        columns=columns,
        rows=rows,
        truncated=truncated,
        row_count=len(rows),
    )
