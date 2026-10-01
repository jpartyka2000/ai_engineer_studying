"""Bronze to silver: parse, normalise, deduplicate, quarantine.

This is where every decision about what the data *means* is made, and each one is made
loudly. Three rules govern the layer:

**Timestamps become UTC instants, or the row is quarantined.** A naive timestamp is not
assumed to be UTC. Guessing a zone shifts an event across a day boundary for every
customer in a negative offset, which turns up later as a daily total that is wrong by one
day's usage and is almost impossible to trace back to here.

**Money stays an integer count of cents.** ``amount_cents`` is parsed with ``int``; a
decimal in that field is a data error, not a value to round. Floats do not sum exactly, so
a warehouse that stores money as a float produces a different total depending on the order
it added things up.

**Duplicates are resolved deterministically.** Upstream delivers at least once, so the same
``event_id`` arrives more than once. The surviving row is the latest ingestion, with
explicit tie-breaks after that, so two runs over the same bronze produce the same silver.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import duckdb

from etlduck.bronze import UNPARSEABLE_MARKER

#: Event types the pipeline understands. An unrecognised type is quarantined rather than
#: passed through, because a rollup that silently includes an unknown kind of event is
#: reporting a number nobody can define.
KNOWN_EVENT_TYPES: frozenset[str] = frozenset({"api_call", "export", "seat_active", "storage_gb"})


@dataclass
class SilverResult:
    """What one silver build did."""

    rows_written: int = 0
    rows_quarantined: int = 0
    duplicates_collapsed: int = 0
    reasons: dict[str, int] = field(default_factory=dict)

    @property
    def rows_considered(self) -> int:
        """Distinct events seen, whether they survived or not."""
        return self.rows_written + self.rows_quarantined

    @property
    def quarantine_fraction(self) -> float:
        """Share of distinct events that failed a rule, 0.0 when there were none."""
        if self.rows_considered == 0:
            return 0.0
        return self.rows_quarantined / self.rows_considered


class RowRejected(ValueError):
    """Raised internally when a bronze row cannot become a silver row."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def parse_instant(raw: str | None) -> datetime:
    """Parse an ISO-8601 timestamp into a UTC instant.

    Accepts an explicit offset or a trailing ``Z``. Rejects a naive timestamp: see the
    module docstring for why guessing is worse than failing.

    Args:
        raw: The raw timestamp text.

    Returns:
        An aware :class:`datetime` in UTC.

    Raises:
        RowRejected: If the value is missing, unparseable, or carries no zone.
    """
    if raw is None or not raw.strip():
        raise RowRejected("missing_timestamp")
    try:
        parsed = datetime.fromisoformat(raw.strip())
    except ValueError as exc:
        raise RowRejected("unparseable_timestamp") from exc
    if parsed.tzinfo is None:
        raise RowRejected("naive_timestamp")
    return parsed.astimezone(timezone.utc)


def parse_cents(raw: str | None) -> int:
    """Parse an integer count of cents.

    Args:
        raw: The raw amount text.

    Returns:
        The amount as an int.

    Raises:
        RowRejected: If the value is missing, not an integer, or negative. A decimal is
            rejected rather than rounded -- the column is cents, so ``"12.50"`` means the
            producer sent dollars and that is worth an alert, not a silent halving.
    """
    if raw is None or not raw.strip():
        raise RowRejected("missing_amount")
    text = raw.strip()
    try:
        value = int(text)
    except ValueError as exc:
        raise RowRejected("amount_not_integer_cents") from exc
    if value < 0:
        raise RowRejected("negative_amount")
    return value


def parse_quantity(raw: str | None) -> int:
    """Parse a non-negative integer quantity.

    Raises:
        RowRejected: If the value is missing, not an integer, or negative.
    """
    if raw is None or not raw.strip():
        raise RowRejected("missing_quantity")
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise RowRejected("quantity_not_integer") from exc
    if value < 0:
        raise RowRejected("negative_quantity")
    return value


def _validated(row: tuple) -> tuple[str, str, str, datetime, int, int]:
    """Turn one deduplicated bronze row into silver values, or reject it.

    Raises:
        RowRejected: With the first rule the row broke. Order is deliberate: identity
            first, because a row with no account cannot be attributed whatever else is
            valid about it.
    """
    event_id, account_id, event_type, occurred_raw, quantity_raw, amount_raw = row

    if event_id is None or not str(event_id).strip():
        raise RowRejected("missing_event_id")
    # Checked before the account, so a line bronze could not parse is reported as what it
    # is rather than as whichever field happens to be absent as a consequence.
    if event_type == UNPARSEABLE_MARKER:
        raise RowRejected("unparseable_source_line")
    if account_id is None or not str(account_id).strip():
        raise RowRejected("missing_account_id")
    if event_type not in KNOWN_EVENT_TYPES:
        raise RowRejected("unknown_event_type")

    occurred_at = parse_instant(occurred_raw)
    quantity = parse_quantity(quantity_raw)
    amount_cents = parse_cents(amount_raw)
    return (
        str(event_id).strip(),
        str(account_id).strip(),
        event_type,
        occurred_at,
        quantity,
        amount_cents,
    )


#: Collapses bronze to one row per event_id. ``ingested_at DESC`` keeps the most recent
#: delivery; ``source_file`` and ``rowid`` break remaining ties, so the choice is total
#: and the same bronze always yields the same silver. Without the final tie-break two runs
#: can disagree whenever one file is delivered twice in the same second.
DEDUPE_SQL = """
SELECT event_id, account_id, event_type, occurred_at_raw, quantity_raw, amount_cents_raw
FROM (
    SELECT *, row_number() OVER (
        PARTITION BY event_id
        ORDER BY ingested_at DESC, source_file ASC, rowid ASC
    ) AS rn
    FROM bronze_usage
)
WHERE rn = 1
ORDER BY event_id
"""


def build_silver(connection: duckdb.DuckDBPyConnection) -> SilverResult:
    """Rebuild ``silver_usage`` and ``quarantine`` from ``bronze_usage``.

    A full rebuild rather than an incremental merge: silver is derived entirely from
    bronze, so rebuilding is both cheaper to reason about and inherently idempotent. The
    tables are replaced inside one transaction, so a reader never sees a half-built silver.

    Args:
        connection: An open warehouse connection.

    Returns:
        A :class:`SilverResult` with the counts and a breakdown of rejection reasons.
    """
    total_bronze = int(connection.execute("SELECT count(*) FROM bronze_usage").fetchone()[0])
    deduped = connection.execute(DEDUPE_SQL).fetchall()
    result = SilverResult(duplicates_collapsed=total_bronze - len(deduped))
    stamp = datetime.now(timezone.utc)

    connection.execute("BEGIN TRANSACTION")
    try:
        connection.execute("DELETE FROM silver_usage")
        connection.execute("DELETE FROM quarantine")
        for row in deduped:
            try:
                event_id, account_id, event_type, occurred_at, quantity, amount_cents = _validated(
                    row
                )
            except RowRejected as rejection:
                connection.execute(
                    "INSERT INTO quarantine (event_id, reason, payload, quarantined_at) "
                    "VALUES (?, ?, ?, ?)",
                    [row[0], rejection.reason, repr(row), stamp],
                )
                result.rows_quarantined += 1
                result.reasons[rejection.reason] = result.reasons.get(rejection.reason, 0) + 1
                continue
            connection.execute(
                "INSERT INTO silver_usage (event_id, account_id, event_type, occurred_at, "
                "event_date, quantity, amount_cents) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    event_id,
                    account_id,
                    event_type,
                    occurred_at,
                    occurred_at.date(),
                    quantity,
                    amount_cents,
                ],
            )
            result.rows_written += 1
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise

    return result
