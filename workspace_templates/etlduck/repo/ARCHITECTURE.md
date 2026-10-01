# Architecture

## The pipeline

```
raw/*.jsonl, raw/accounts*.csv
  │
  ├─ bronze.ingest_all        verbatim copy; every column text; load_log keyed on content
  │
  ├─ silver.build_silver      parse, normalise to UTC, dedupe, quarantine with a reason
  │
  ├─ gold.build_gold          one row per (date, account), joined to the collapsed dimension
  │
  ├─ quality.run_all          six gates; the reconciliation is the one that matters
  │
  └─ watermark.advance        only after the gates pass, only ever forwards
```

`pipeline.run_pipeline` is the only thing that owns the watermark. A layer rebuilt on its own
cannot mark work as done, which is pinned by `test_gold_does_not_touch_the_watermark`.

## Why each layer exists

**Bronze keeps what arrived.** It coerces nothing: a quantity sent as a JSON number is stored
as the string `"7"`. A line that is not valid JSON is still stored, with `event_type` set to
`__unparseable__`, because bronze is the only place that will ever know that line existed.
Dropping it here would make a truncated delivery undetectable.

**Silver decides what things mean.** Every decision is loud — see "Nothing is guessed" below.
It is a **full rebuild** from bronze rather than an incremental merge, because silver is a
pure function of bronze; rebuilding is both easier to reason about and idempotent without any
merge logic to get wrong.

**Gold is a pure function of silver**, rebuilt the same way, inside one transaction so a
reader never sees a half-built table.

## Idempotency, three different ways

The three layers achieve it by three different mechanisms, and it is worth knowing which is
which when one of them breaks.

| Layer | Mechanism | What breaks it |
|---|---|---|
| bronze | `load_log` on `(source_file, content_hash)`, written in the row transaction | Checking the log outside the transaction, or keying on the filename alone |
| silver | full rebuild, `DELETE` then insert in one transaction | Switching to an append, or to a merge without a key |
| gold | full rebuild from silver | Joining an undeduplicated dimension — see below |

The content hash matters in both directions. Keying on the filename alone would skip a
corrected re-export, which loses data; keying on the modification time would reload a
byte-identical re-delivery, which duplicates it.

## The fan-out, which is the easiest way to inflate revenue

`bronze_accounts` holds **one row per delivery**, so an account that appears in two exports
appears twice. Joining `silver_usage` to that table multiplies every event for that account
by the number of deliveries. It looks like growth, nothing raises, and the only thing that
catches it is `gold_reconciles_with_silver`.

So `gold.ROLLUP_SQL` joins `LATEST_ACCOUNTS_SQL`, a `row_number()` view that keeps one row
per account. The committed sample data contains this case on purpose: `accounts_delta.csv`
re-delivers two accounts, so bronze holds ten rows for eight accounts.

The join is a `LEFT JOIN`. Usage for an account missing from the dimension is counted with a
`NULL` plan rather than dropped — losing revenue because a dimension export was late is worse
than reporting it as unattributed, and `no_unattributed_usage` reports it either way.

## Nothing is guessed

Silver rejects rather than assumes, and each rejection has its own reason so a report says
what changed upstream rather than just that something did.

- **A naive timestamp is `naive_timestamp`, not assumed UTC.** Assuming shifts an event
  across a day boundary for every customer in a negative offset. In the sample data 58 of 400
  events are close enough to midnight for this to move them.
- **A decimal in `amount_cents` is `amount_not_integer_cents`, not rounded.** The column is
  cents, so `"12.50"` means the producer sent dollars — worth an alert, not a silent
  hundred-fold error.
- **An unrecognised `event_type` is `unknown_event_type`, not passed through.** A rollup that
  includes a kind of event nobody can define is a number nobody can defend.
- **A line bronze could not parse is `unparseable_source_line`**, checked before the
  account-id rule so it is reported as what it is rather than as whichever field is absent as
  a consequence.

Quarantined rows are kept in a table and counted. The budget is 5% and deliberately not zero:
a handful of malformed rows is normal, and blocking the pipeline on them would mean no
warehouse at all on a bad day. The committed data sits at 2.44%, well inside it, so an
unrelated change cannot trip the gate.

## Determinism

Hash randomisation is on by default in Python and SQL has no inherent row order, so anything
resolved arbitrarily differs between runs. Every such place is resolved explicitly:

- **Deduplication** orders by `ingested_at DESC, source_file ASC, rowid ASC`. The first term
  is the business rule — the latest delivery wins. The other two exist because two files can
  be ingested in the same second, and without them two rebuilds of the same bronze can
  disagree. `test_deduplication_is_deterministic_across_rebuilds` is the one that fails
  intermittently if they are removed, which is the worst way for a test to fail.
- **The account dimension** is collapsed with the same ordering.
- **`ingest_all`** processes files in sorted order, so a partial failure leaves a predictable
  prefix loaded rather than an arbitrary subset.
- **Profiling output** is sorted, because it is read by a human diffing today's report against
  yesterday's.

## Watermarks

A watermark is about **event time**, not files and not wall-clock time. `max_event_time`
reads the newest instant actually present in silver. Usage telemetry arrives late as a matter
of course, so a watermark set to "now" skips whatever is still in flight.

Two rules, both enforced in code rather than by convention:

1. `advance_watermark` **raises** on a backwards move rather than clamping. A caller computing
   an earlier position has a bug, and keeping the old value silently hides it until somebody
   asks why a backfill produced nothing.
2. `watermark_advanced_on_success` runs the work **first** and advances afterwards. Advancing
   first means an exception leaves the watermark past data that was never processed, and that
   window is never looked at again.

`strict=False` on `run_pipeline` changes whether a failing gate raises. It does **not** change
whether the watermark moves — it never moves on a failed run. The flag is for inspecting a
broken warehouse, not for getting past the gate.

## Numeric choices worth knowing

- **Money is `BIGINT` cents.** Never a float, never a `DECIMAL` that a driver might hand back
  as a float. The reconciliation compares integers with no tolerance.
- **Timestamps are UTC instants**; `silver_usage.event_date` is derived from the instant and
  `dates_are_utc_consistent` re-derives it to check. DuckDB returns naive datetimes for
  `TIMESTAMP` columns, so the watermark code reattaches UTC on read — restoring information
  that was there, not assuming it.
- **Quantities are integers.** A fractional quantity is a producer error, quarantined.

## The Databricks shape

`jobs/*.yaml`, `dbx_conf/cluster_policy.json` and `notebooks/*.py` mirror the platform team's
real assets. CI parses all three — the jobs must declare a name and tasks, the policy must pin
`spark.sql.session.timeZone` to UTC, and the notebooks must keep their
`# COMMAND ----------` delimiters and stay valid Python. They are documentation that is
checked, which is the only kind that stays true.

`spark_compat.LocalSession` is a four-method façade so the notebooks read like Spark and run
without a JVM. It is deliberately minuscule; anything more becomes a half-reimplementation of
a distributed engine, which is a far worse thing to own than some SQL.

## Testing

`tests/` has two kinds of test and they need different fixtures. Unit-level tests build their
own tiny landing zone with `write_usage` / `write_accounts`, so an assertion can name every
row that went in, and numeric expectations are hand-computed with the arithmetic in the
docstring. Integration-level tests run against the committed `raw/` and assert exact totals,
which is only honest because the generator is seeded.

Every quality gate is tested **in both directions** — passing on good data and failing on data
built to break it. A gate that has only ever been seen to pass is not known to work.
