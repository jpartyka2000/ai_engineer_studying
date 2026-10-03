"""The audit trail.

Three rules, each of which exists because the obvious alternative makes the trail
useless at exactly the moment somebody needs it.

**Log the SQL that ran, not the SQL that was generated.** The generated statement is what
the model proposed; the rewritten one is what touched the database. An audit record
holding the former tells an investigator what we were asked to do, not what we did, and
the difference between those two is the entire subject of any incident here.

**Log on the rejection path too.** A refused query is the single most interesting event
this service produces -- it is the one where somebody tried something. A trail that
records only successes describes a service where nothing has ever gone wrong.

**Log before returning rows, not after.** Writing the record after the result set comes
back means a query that times out, errors, or returns ten million rows leaves no trace,
which inverts the relationship between how alarming an event is and how likely it is to
be recorded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

logger = logging.getLogger("sqlgenie.audit")


class Outcome(StrEnum):
    """What happened to a request."""

    EXECUTED = "executed"
    REFUSED = "refused"
    FAILED = "failed"


@dataclass(frozen=True)
class AuditRecord:
    """One auditable event.

    Attributes:
        tenant_id: The tenant the request was bound to.
        question: The natural-language question as asked.
        generated_sql: What the model produced, before rewriting.
        executed_sql: What actually ran, after the tenant predicate was applied.
            ``None`` when nothing ran.
        outcome: Executed, refused, or failed.
        base_tables: Base tables the statement read.
        predicates_added: Tenant predicates the policy inserted.
        reason: Why it was refused or how it failed.
        row_count: Rows returned, when it ran.
        at: When the record was made, UTC.
    """

    tenant_id: str
    question: str
    generated_sql: str
    executed_sql: str | None
    outcome: Outcome
    base_tables: tuple[str, ...] = ()
    predicates_added: int = 0
    reason: str = ""
    row_count: int | None = None
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict[str, Any]:
        """Return the record as a JSON-serialisable dict."""
        return {
            "tenant_id": self.tenant_id,
            "question": self.question,
            "generated_sql": self.generated_sql,
            "executed_sql": self.executed_sql,
            "outcome": str(self.outcome),
            "base_tables": list(self.base_tables),
            "predicates_added": self.predicates_added,
            "reason": self.reason,
            "row_count": self.row_count,
            "at": self.at.isoformat(),
        }


#: In-process sink. A real deployment ships these to a log pipeline; keeping them here
#: as well is what lets the security suite assert that an attempt was recorded, which is
#: a property worth testing rather than trusting.
_records: list[AuditRecord] = []


def record(entry: AuditRecord) -> AuditRecord:
    """Append a record and emit it to the logger.

    Args:
        entry: The record.

    Returns:
        The same record, so callers can log and return in one expression.
    """
    _records.append(entry)
    logger.info(
        "%s tenant=%s tables=%s predicates=%d rows=%s %s",
        entry.outcome,
        entry.tenant_id,
        ",".join(entry.base_tables) or "-",
        entry.predicates_added,
        entry.row_count if entry.row_count is not None else "-",
        entry.reason,
    )
    return entry


def records(*, tenant_id: str | None = None) -> list[AuditRecord]:
    """Return recorded events, newest last.

    Args:
        tenant_id: Restrict to one tenant.

    Returns:
        The matching records.
    """
    if tenant_id is None:
        return list(_records)
    return [entry for entry in _records if entry.tenant_id == tenant_id]


def clear() -> None:
    """Empty the in-process sink. For tests."""
    _records.clear()
