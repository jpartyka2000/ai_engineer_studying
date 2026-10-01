# etlduck

A medallion warehouse for usage and billing data. Raw exports land in `raw/`, are copied
verbatim into **bronze**, parsed and normalised into **silver**, and rolled up into **gold**.

**There is no cluster.** The warehouse is a single DuckDB file under `warehouse/` and the
whole pipeline runs in one local process. The job definitions in `jobs/`, the cluster policy
in `dbx_conf/` and the cell-delimited scripts in `notebooks/` are shaped like the platform
team's real Databricks assets, because that is the shape anyone working here has to read —
but nothing in this repository talks to Databricks. `src/etlduck/spark_compat.py` says so at
length.

## Getting started

```bash
docker compose up -d --wait   # or: make up
make test
make run
```

## Common tasks

| Command | What it does |
|---|---|
| `make test` | Full suite. **This is what grading runs.** |
| `make run` | The whole pipeline, then the quality gates, then the watermark |
| `make profile` | Describe the landing-zone files *before* ingesting them |
| `make check` | Run the data-quality gates against the current warehouse |
| `make bench` | Measure how much work a run does |
| `make seed` | Regenerate the committed landing-zone files |
| `make ci` | Run the CI pipeline locally (`ci/run_ci.sh`) |

The layers can also be run one at a time — `etlduck bronze`, `etlduck silver`,
`etlduck gold` — which is how you narrow down which one is wrong.

## The layers

```
raw/            whatever the upstream dropped. JSONL usage events, CSV account dimension.
  ↓ bronze      a verbatim copy. Every column is text and named *_raw to say so.
  ↓ silver      parsed, normalised to UTC, deduplicated. Bad rows go to quarantine.
  ↓ gold        one row per (date, account), joined to the latest account dimension.
```

Bronze exists so a malformed delivery is still recoverable: it keeps the line. Silver is
where every decision about what the data *means* is made, and each one is made loudly —
anything it cannot parse is written to `quarantine` with a reason and counted, never dropped.
Gold is a pure function of silver, so it is rebuilt rather than merged.

## Four properties this package is built around

Each one has tests named after it, and each is a thing that goes wrong silently in a
warehouse rather than loudly.

**Idempotency.** Re-running a load does not duplicate rows. `load_log` is keyed on
`(source_file, content_hash)` and written in the same transaction as the rows themselves, so
a retried job inserts nothing and a *corrected* re-export under the same filename is still
loaded. Silver and gold are full rebuilds, which makes them idempotent by construction.

**Monotonic watermarks.** A watermark records how far through *event time* a stream has been
processed. It never moves backwards, and it only advances over work that passed its quality
gates. Both failures look identical in production — a day with less data than expected — and
one of them never heals, because from then on the pipeline is consistently looking past the
window it skipped.

**Determinism.** Every tie-break is explicit. Deduplication keeps the latest ingestion and
then breaks ties on `source_file` and `rowid`; the account dimension is collapsed the same
way. Two runs over the same input produce byte-identical output, which is what lets the tests
assert constants.

**Loud rejection.** Nothing is guessed. A naive timestamp is quarantined rather than assumed
to be UTC. A decimal in `amount_cents` is quarantined rather than rounded. An unknown event
type is quarantined rather than passed through into a total nobody can define.

## Money and time

**Money is an integer count of cents, everywhere.** Floats do not sum exactly, so a
warehouse that stores money as a float gives a different total depending on the order it
added things up. `gold_reconciles_with_silver` compares the two layers as integers, with no
tolerance, because none is needed.

**Every timestamp is a UTC instant and every date is derived from one.** The upstream sends
mixed offsets — `+00:00`, `-05:00`, `+05:30`, `Z` — and in the committed sample data **58 of
400 events fall on a different UTC date than the local date in their raw timestamp**. A date
computed in the wrong zone therefore misstates a day's revenue by a slice big enough to
matter and small enough to read as noise. Two days of deliveries legitimately produce four
UTC dates, with thin tails at each end; that is correct, not a bug.

## The data

`raw/` holds files produced by `tools/gen_seed_data.py` with a fixed seed, which is why the
tests can assert exact totals: 400 silver rows, 30 gold rows, 817,691 cents. The defects in
them are deliberate and fixed — per day, one unparseable line, one naive timestamp, one
unknown event type, one decimal amount and one event with no account, plus one event replayed
across days because the upstream delivers at least once. The account dimension arrives in two
files, so an account appears twice in bronze and the dimension has to be collapsed before it
is joined.

If a number in the suite ever needs changing rather than explaining, something regenerated
the data; find out what, rather than updating the constant.

Large volumes go to a scratch directory: `python tools/gen_seed_data.py --out /tmp/big
--events-per-day 20000`. That is what `make bench` does.

## CI

`.github/workflows/ci.yml` is what GitHub runs; `ci/run_ci.sh` is an executable mirror and is
what runs locally and in grading. **Change one and you must change the other.** The pipeline
smoke test lives in `ci/pipeline_smoke.sh` so both call the same file rather than each
carrying a copy.

See `ARCHITECTURE.md` for the layer contracts and the numeric choices.
