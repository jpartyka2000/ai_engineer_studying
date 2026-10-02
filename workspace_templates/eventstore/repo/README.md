# eventstore

Request-event ingestion for an API gateway fleet, and the performance model built on it.

The gateway sends us one event per served HTTP request. We keep the raw stream in
**MongoDB** and maintain minute-grain rollups in **DuckDB**, which is where every chart,
SLO report and deploy comparison is answered from.

```
gateway ──POST /v1/events──▶  MongoDB  ──rollup──▶  DuckDB  ──▶  /v1/stats/*
                             (operational)        (analytical)
```

## Getting started

```bash
cp .env.example .env        # only needed if you are not using the exercise harness
make up                     # build the image, start MongoDB and the API
make load                   # load the committed event exports
make rollup                 # build the warehouse from them
make test                   # run the suite
```

`make help` lists every target.

The API is on the port in your `.env` (`WS_APP_PORT`); `http://localhost:$WS_APP_PORT/docs`
has the generated OpenAPI page.

## Layout

| Path | What lives there |
|---|---|
| `src/eventstore/api.py` | The HTTP surface. Handlers parse a window and serialise a result; they do no arithmetic. |
| `src/eventstore/ingest.py` | The write path, including deduplication. |
| `src/eventstore/queries.py` | The operational read path. Every query here is bounded. |
| `src/eventstore/rollup.py` | The Mongo → DuckDB pipeline and its watermark. |
| `src/eventstore/analytics.py` | The seam: turns a question into a window, a query and a statistic. |
| `src/eventstore/perfmodel/` | **The statistics.** Pure functions over numbers; no storage, no I/O. |
| `data/` | Three hours of committed event exports, produced by `tools/gen_seed_data.py`. |
| `bench/` | What the server had to *do*, measured in work rather than milliseconds. |

## The two stores

This is the part worth understanding before changing anything; `ARCHITECTURE.md` has
the long version.

**MongoDB is operational.** It holds the raw stream, is written to constantly, and is
read by id and by recent time window. No request handler ever scans it.

**DuckDB is analytical.** It holds `fact_requests` and the `rollup_minute` aggregates,
and it is entirely derived state — delete the file and `eventstore rollup --full`
rebuilds it. That is why `warehouse/*.duckdb` is gitignored.

## The statistics

Everything under `perfmodel/` is a pure function of numbers, which is what lets each one
be tested against a constant derived by hand in the test's own docstring rather than
against a snapshot nobody can check.

| Module | Question |
|---|---|
| `percentiles` | How slow was the slow end? Nearest-rank p50/p95/p99 — always a real observation. |
| `apdex` | How many users were unhappy? Satisfied / tolerating / frustrated against a target. |
| `intervals` | How sure are we? Wilson for rates, seeded bootstrap for everything else. |
| `nonparametric` | Is this release slower than that one? Mann-Whitney U, tie-corrected. |
| `changepoint` | Did it change and stay changed? EWMA for incidents, CUSUM for deploys. |
| `baseline` | Is this unusual *for a Tuesday*? Hour-of-week buckets, median and MAD. |

No numpy, no scipy, no pandas — see the note at the top of `requirements.txt`.

## Running the tests

```bash
make test        # everything, inside the container
make test-unit   # only the tests that need no database
```

Tests that need MongoDB are marked `mongo` and each runs against **its own database**,
dropped afterwards. A missing MongoDB makes them **fail rather than skip**: a skipped
test is green, and a suite that goes green when the database is unreachable cannot tell
"this works" from "this never ran".

## CI

`ci/run_ci.sh` is the executable mirror of `.github/workflows/ci.yml`. There is no
GitHub runner here, so the workflow is the artifact you read and the script is what
actually runs — by `make ci` and by the grading harness. Change one and you must change
the other.
