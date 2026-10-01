"""DuckDB connection handling and the warehouse schema.

One place creates tables, so a column added here cannot disagree with what a job expects.
The schema is applied on every connect and is written to be safe to re-apply --
``CREATE TABLE IF NOT EXISTS`` throughout -- because an ETL job is restarted far more
often than it is first run.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import duckdb

from etlduck.config import Paths, paths

#: Applied on every connect. Idempotent by construction: re-running it is a no-op, which
#: is what lets any job open the warehouse without first asking whether it is new.
SCHEMA = """
CREATE TABLE IF NOT EXISTS bronze_usage (
    event_id        VARCHAR NOT NULL,
    account_id      VARCHAR,
    event_type      VARCHAR,
    occurred_at_raw VARCHAR,
    quantity_raw    VARCHAR,
    amount_cents_raw VARCHAR,
    source_file     VARCHAR NOT NULL,
    ingested_at     TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze_accounts (
    account_id  VARCHAR NOT NULL,
    name        VARCHAR,
    plan        VARCHAR,
    country     VARCHAR,
    source_file VARCHAR NOT NULL,
    ingested_at TIMESTAMP NOT NULL
);

-- One row per file successfully loaded. The content hash is part of the key so a file
-- that is re-exported with different contents under the same name is treated as new,
-- while a byte-identical re-delivery is skipped.
CREATE TABLE IF NOT EXISTS load_log (
    source_file  VARCHAR NOT NULL,
    content_hash VARCHAR NOT NULL,
    row_count    BIGINT  NOT NULL,
    loaded_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (source_file, content_hash)
);

CREATE TABLE IF NOT EXISTS silver_usage (
    event_id     VARCHAR NOT NULL PRIMARY KEY,
    account_id   VARCHAR NOT NULL,
    event_type   VARCHAR NOT NULL,
    occurred_at  TIMESTAMP NOT NULL,   -- UTC, always
    event_date   DATE NOT NULL,        -- derived from the UTC instant
    quantity     INTEGER NOT NULL,
    amount_cents BIGINT NOT NULL       -- integer cents, never a float
);

-- Rows that failed a quality rule. Kept rather than dropped: a pipeline that discards
-- what it cannot parse reports clean numbers over an unknown amount of missing data.
CREATE TABLE IF NOT EXISTS quarantine (
    event_id   VARCHAR,
    reason     VARCHAR NOT NULL,
    payload    VARCHAR,
    quarantined_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS gold_daily_usage (
    event_date   DATE NOT NULL,
    account_id   VARCHAR NOT NULL,
    plan         VARCHAR,
    events       BIGINT NOT NULL,
    quantity     BIGINT NOT NULL,
    amount_cents BIGINT NOT NULL,
    PRIMARY KEY (event_date, account_id)
);

-- Incremental state, one row per named stream. Separate from load_log because a
-- watermark is about *event time* while the load log is about *files*.
CREATE TABLE IF NOT EXISTS watermarks (
    stream      VARCHAR NOT NULL PRIMARY KEY,
    position    TIMESTAMP NOT NULL,
    updated_at  TIMESTAMP NOT NULL
);
"""


def connect(root: str | Path | None = None, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open the warehouse, applying the schema.

    Args:
        root: Project root override, for tests.
        read_only: Open without the ability to write. The schema is not applied in this
            mode, because applying it would be a write.

    Returns:
        An open connection. The caller closes it, or uses :func:`warehouse`.
    """
    resolved: Paths = paths(root).ensure()
    connection = duckdb.connect(str(resolved.database), read_only=read_only)
    if not read_only:
        connection.execute(SCHEMA)
    return connection


@contextmanager
def warehouse(
    root: str | Path | None = None, read_only: bool = False
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Context manager around :func:`connect`.

    DuckDB holds an exclusive lock on the database file, so leaking a connection makes
    every later run fail with a lock error rather than anything that points at the leak.
    """
    connection = connect(root, read_only=read_only)
    try:
        yield connection
    finally:
        connection.close()


def table_count(connection: duckdb.DuckDBPyConnection, table: str) -> int:
    """Return the row count of a table.

    Args:
        connection: An open connection.
        table: Table name. Interpolated, so it must not come from user input -- every
            call site in this package passes a literal.

    Returns:
        The number of rows.
    """
    return int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])  # noqa: S608
