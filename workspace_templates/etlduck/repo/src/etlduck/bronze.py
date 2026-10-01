"""Raw landing zone to bronze.

Bronze is a faithful copy of what arrived. Nothing is parsed, coerced or rejected here --
every value lands as text, and the columns are named ``*_raw`` to say so. Cleaning happens
in silver, where a rejected row can be quarantined with a reason.

**The property that matters in this layer is idempotency.** Re-running a load must not
duplicate rows. Upstream exports get re-delivered, jobs get retried, and a backfill will
replay a month of files over a warehouse that already holds some of them.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from etlduck.config import paths

#: Written into ``event_type`` for a line bronze could not parse. Bronze keeps the line --
#: losing the only evidence a malformed delivery arrived is worse than carrying it one layer
#: further -- and silver quarantines it under its own reason.
UNPARSEABLE_MARKER = "__unparseable__"


@dataclass(frozen=True)
class LoadResult:
    """What one file's load did."""

    source_file: str
    rows_inserted: int
    skipped_as_duplicate: bool

    @property
    def loaded(self) -> bool:
        """Whether this call actually wrote anything."""
        return not self.skipped_as_duplicate


def content_hash(path: Path) -> str:
    """Return a stable hash of a file's bytes.

    Read in chunks so a large export does not have to fit in memory. SHA-256 rather than
    a modification time: a re-export with identical contents should be recognised as the
    same delivery even though its mtime changed, and a changed file under the same name
    must not be mistaken for one already loaded.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def already_loaded(connection: duckdb.DuckDBPyConnection, source_file: str, digest: str) -> bool:
    """Return whether this exact file content has been loaded before.

    Args:
        connection: An open warehouse connection.
        source_file: The file's name as recorded in ``load_log``.
        digest: Its content hash.

    Returns:
        Whether a matching row exists in ``load_log``.
    """
    row = connection.execute(
        "SELECT 1 FROM load_log WHERE source_file = ? AND content_hash = ?",
        [source_file, digest],
    ).fetchone()
    return row is not None


def _record_load(
    connection: duckdb.DuckDBPyConnection, source_file: str, digest: str, rows: int
) -> None:
    """Mark a file as loaded, in the same transaction as the rows themselves."""
    connection.execute(
        "INSERT INTO load_log (source_file, content_hash, row_count, loaded_at) "
        "VALUES (?, ?, ?, ?)",
        [source_file, digest, rows, datetime.now(timezone.utc)],
    )


def read_usage_jsonl(path: Path) -> list[dict[str, str | None]]:
    """Read a usage export, one JSON object per line.

    A line that is not valid JSON is **not** skipped here. It is turned into a row whose
    fields are all empty except a marker, so silver can quarantine it with a reason.
    Dropping it in bronze would lose the only evidence it ever arrived.

    Args:
        path: The ``.jsonl`` file.

    Returns:
        One dict per line, every value a string or None.
    """
    rows: list[dict[str, str | None]] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except ValueError:
                rows.append(
                    {
                        "event_id": f"{path.name}:{number}",
                        "account_id": None,
                        "event_type": UNPARSEABLE_MARKER,
                        "occurred_at_raw": None,
                        "quantity_raw": None,
                        "amount_cents_raw": None,
                    }
                )
                continue
            rows.append(
                {
                    "event_id": _text(record.get("event_id")),
                    "account_id": _text(record.get("account_id")),
                    "event_type": _text(record.get("event_type")),
                    "occurred_at_raw": _text(record.get("occurred_at")),
                    "quantity_raw": _text(record.get("quantity")),
                    "amount_cents_raw": _text(record.get("amount_cents")),
                }
            )
    return rows


def read_accounts_csv(path: Path) -> list[dict[str, str | None]]:
    """Read the account dimension export.

    Args:
        path: The ``.csv`` file.

    Returns:
        One dict per row, every value a string or None.
    """
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return [
            {
                "account_id": _text(row.get("account_id")),
                "name": _text(row.get("name")),
                "plan": _text(row.get("plan")),
                "country": _text(row.get("country")),
            }
            for row in reader
        ]


def _text(value: object) -> str | None:
    """Return a value as text, preserving None. Bronze stores everything as text."""
    if value is None:
        return None
    return str(value)


def load_usage_file(
    connection: duckdb.DuckDBPyConnection, path: Path, ingested_at: datetime | None = None
) -> LoadResult:
    """Load one usage export into ``bronze_usage``, at most once.

    The load log is consulted first and written in the same transaction as the rows, so a
    crash between the two cannot leave a file recorded as loaded with none of its rows
    present -- or its rows present with no record, which is what makes a retry duplicate
    everything.

    Args:
        connection: An open warehouse connection.
        path: The file to load.
        ingested_at: Override the ingestion timestamp. Tests pass it for determinism.

    Returns:
        A :class:`LoadResult`. Check ``skipped_as_duplicate`` rather than the row count,
        because a legitimately empty file also inserts zero rows.
    """
    digest = content_hash(path)
    if already_loaded(connection, path.name, digest):
        return LoadResult(source_file=path.name, rows_inserted=0, skipped_as_duplicate=True)

    rows = read_usage_jsonl(path)
    stamp = ingested_at or datetime.now(timezone.utc)

    connection.execute("BEGIN TRANSACTION")
    try:
        for row in rows:
            connection.execute(
                "INSERT INTO bronze_usage (event_id, account_id, event_type, "
                "occurred_at_raw, quantity_raw, amount_cents_raw, source_file, ingested_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    row["event_id"],
                    row["account_id"],
                    row["event_type"],
                    row["occurred_at_raw"],
                    row["quantity_raw"],
                    row["amount_cents_raw"],
                    path.name,
                    stamp,
                ],
            )
        _record_load(connection, path.name, digest, len(rows))
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise

    return LoadResult(source_file=path.name, rows_inserted=len(rows), skipped_as_duplicate=False)


def load_accounts_file(
    connection: duckdb.DuckDBPyConnection, path: Path, ingested_at: datetime | None = None
) -> LoadResult:
    """Load the account dimension into ``bronze_accounts``, at most once.

    Args:
        connection: An open warehouse connection.
        path: The CSV to load.
        ingested_at: Override the ingestion timestamp.

    Returns:
        A :class:`LoadResult`.
    """
    digest = content_hash(path)
    if already_loaded(connection, path.name, digest):
        return LoadResult(source_file=path.name, rows_inserted=0, skipped_as_duplicate=True)

    rows = read_accounts_csv(path)
    stamp = ingested_at or datetime.now(timezone.utc)

    connection.execute("BEGIN TRANSACTION")
    try:
        for row in rows:
            connection.execute(
                "INSERT INTO bronze_accounts (account_id, name, plan, country, source_file, "
                "ingested_at) VALUES (?, ?, ?, ?, ?, ?)",
                [row["account_id"], row["name"], row["plan"], row["country"], path.name, stamp],
            )
        _record_load(connection, path.name, digest, len(rows))
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise

    return LoadResult(source_file=path.name, rows_inserted=len(rows), skipped_as_duplicate=False)


def ingest_all(
    connection: duckdb.DuckDBPyConnection,
    root: str | Path | None = None,
    ingested_at: datetime | None = None,
) -> list[LoadResult]:
    """Load every file in the landing zone that has not been loaded already.

    Files are processed in sorted order so a run is reproducible and so a partial failure
    leaves a predictable prefix loaded rather than an arbitrary subset.

    Args:
        connection: An open warehouse connection.
        root: Project root override.
        ingested_at: Override the ingestion timestamp.

    Returns:
        One :class:`LoadResult` per file considered, in the order processed.
    """
    landing = paths(root).ensure().raw
    results: list[LoadResult] = []
    for path in sorted(landing.glob("accounts*.csv")):
        results.append(load_accounts_file(connection, path, ingested_at))
    for path in sorted(landing.glob("usage_events_*.jsonl")):
        results.append(load_usage_file(connection, path, ingested_at))
    return results
