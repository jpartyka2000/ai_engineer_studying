# Architecture

Why this service is shaped the way it is. Read this before changing the storage layer or
anything under `perfmodel/`.

## Two stores, and the line between them

| | MongoDB `events` | DuckDB |
|---|---|---|
| Role | Operational | Analytical |
| Holds | The raw event stream | `fact_requests` + `rollup_minute` |
| Written by | `/v1/events` | The rollup job, and nothing else |
| Read by | `/v1/events/*` | `/v1/stats/*` |
| Access shape | Point and recent-range, index-served | Scans, aggregates, time series |
| Durability | **The system of record** | Derived; delete it and rebuild |

The split is the ordinary one, made explicit. Mongo is good at a high-rate write path
and at reading a recent window; it is not where you want to scan a month of events to
draw a chart, and an analytical query that does so takes the write path down with it.
DuckDB is columnar and in-process, so a month of minute buckets is a few milliseconds
and there is no second server to operate.

**The rule: a request handler never scans Mongo, and nothing but the rollup writes
DuckDB.** If a statistics endpoint ever starts answering before the rollup has run,
something has crossed that line. `tests/test_api.py::test_statistics_come_from_the_
warehouse_not_the_event_stream` is there to catch it.

## Two clocks

Every event carries two timestamps and almost every subtle bug in a pipeline like this
one comes from confusing them.

`occurred_at` — **event time.** When the request was served. Every analytical question is
asked in event time, because that is the only timeline a user experienced. Buckets,
percentiles, baselines and comparisons are all event time.

`received_at` — **ingest time.** When *we* accepted the event. Stamped by us, never by
the client: a producer that can set it can reorder our pipeline. One stamp per delivered
batch, because the events in a batch arrived together and microsecond-apart stamps would
imply an ordering the network never provided.

**The rollup's watermark runs on ingest time.** This is the single most important design
decision in the service. Events arrive late — a gateway buffering through a network
partition delivers a twenty-minute-old batch — and the minute they belong to has already
been rolled up and reported. Tracking ingest time means the next run sees the batch
arrive and rebuilds the minute it belongs to. Tracking event time would mean the
watermark has already moved past that minute and will never select it again.

The failure mode is what makes it worth writing down: **nothing goes red.** Totals for
the current window stay perfectly plausible. The only visible symptom is that a number
somebody exported last week no longer matches the number they export today.

The watermark is also **inclusive** (`$gte`), not exclusive. A whole ingest batch shares
one `received_at`, so an exclusive watermark combined with a batch limit can cut a tie
group in half and skip its remainder forever. Inclusive re-reads the boundary batch on
every run, which is free because the sink is keyed on `event_id`. At-least-once with an
idempotent sink beats exactly-once with a subtle hole in it.

## Deduplication is the database's job

A gateway that times out retries, so duplicate batches are normal traffic rather than an
error. The unique index on `event_id` is what absorbs them, and the application counts
duplicate-key errors rather than preventing them.

The obvious alternative — query for the ids already present, then insert the rest — is a
race by construction: two workers replaying the same batch both see "absent" and both
insert. Only the database can arbitrate. The same guarantee is restated on the DuckDB
side, where `fact_requests` is keyed on `event_id` and loaded with `INSERT OR REPLACE`.

## Rollups are rebuilt, not incremented

A late event belongs to an old minute whose aggregate has already been written.
Recomputing every bucket a load touched — rather than incrementing counters — is what
lets a late arrival correct history instead of being added to whatever bucket happens to
be current. It also means a bucket emptied by a deletion disappears rather than keeping
the traffic it used to have.

Percentiles are stored in `rollup_minute` rather than recomputed on read, because the raw
latencies behind a bucket are what make a month of history large, and because a stored
p95 is the number the SLO report cited at the time.

They are computed in Python by `perfmodel.percentiles.summarize`, not by DuckDB's
`quantile_disc`. The two use different rank conventions, and **a system with two
definitions of p95 is a system whose dashboard and whose SLO report disagree by one
observation and nobody can say which is right.**

## The performance model is pure

Nothing under `src/eventstore/perfmodel/` imports `mongo`, `duck` or `api`. The payoff is
that every statistic can be tested against a hand-computed constant rather than against
whatever happens to be in the database today, and can be reviewed by someone who does not
know where the data came from.

Three choices inside it are worth defending explicitly, because each has an obvious
alternative that is wrong in a way that does not announce itself:

**Nearest-rank percentiles, not interpolated.** A reported p99 should be a latency some
request actually experienced. Interpolation invents a number between two samples, and
when an SLO is written as "p99 under 400ms" the thing it is compared against ought to be
a measurement.

**Wilson intervals, not the normal approximation.** Error rates live near zero, where the
normal approximation gives negative lower bounds and, at zero errors, an interval of zero
width — "0% ± 0%" after five requests. Wilson has no degenerate case.

**Median and MAD, not mean and standard deviation.** The history a baseline is fitted from
contains last month's incident, because incidents are what happened. A standard deviation
inflated by one incident is exactly what stops the next one from scoring above threshold;
a MAD needs half the history to be anomalous before it moves. `tests/test_baseline.py`
works the arithmetic for both on the same data: z = 1.73 against z = 134.56.

**Mann-Whitney, not a t-test.** Latency is bounded below, unbounded above and heavily
right-skewed, so a mean is dominated by the tail. A rank test asks the question a deploy
decision actually turns on: pick one request from each release at random — which is
slower?

**CUSUM for deploys, EWMA for incidents.** EWMA's memory decays geometrically, so it
catches a spike and misses a small sustained shift: against a one-sigma step its weighted
mean converges to one sigma against a 1.26-sigma band and never alarms at all. CUSUM
accumulates, so the same shift crosses its decision interval after eleven observations.
`tests/test_changepoint.py` pins both numbers.

## What is deliberately not here

**No numpy, scipy or pandas.** Every number this service reports is arithmetic you can
check by hand, which is what makes the tests assert constants rather than snapshots.

**No ORM.** Two stores with two very different access shapes; an abstraction over both
would hide exactly the differences this design is built around.

**No background scheduler.** The rollup is a CLI subcommand and an endpoint. What runs it
on a timer is a deployment concern, and keeping it out of the process means the pipeline
can be driven by a test.
