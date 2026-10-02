#!/usr/bin/env python3
"""Generate the committed event exports.

**The generator is committed, the data is too, and the seed is fixed.** Every number the
integration tests assert -- 1464 rows across three exports, 1440 unique event ids, 16 of
them late -- is a consequence of the constants in this file. If one of those numbers ever
has to be "fixed" rather than explained, something regenerated the data and the right
response is to find out why, not to update the constant.

What the three hours of traffic contain, and why:

**A deploy at 12:30.** ``checkout`` ships a release that adds roughly 90ms to the middle
of its latency distribution and rather more to the tail. The shift is small enough that
no single request looks wrong, which is the point: it is there to be found by comparing
distributions, not by looking at a chart.

**Late arrivals.** One gateway buffers through a network blip between 11:40 and 11:42 and
delivers those events 25 minutes after they happened. They are the reason the rollup
tracks ingest time rather than event time, and they are what a pipeline that confuses the
two silently loses.

**A duplicate delivery.** The 12:00 export repeats the last 24 events of the 11:00 one,
as a retried batch would. The unique index absorbs them.

**A quiet route.** ``auth`` ``/v1/token/introspect`` gets a handful of requests per hour,
so that any statistic computed over it has a small ``n`` -- which is where naive
confidence intervals fall over.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

#: Fixed so that every environment generates byte-identical files.
SEED = 20260401

#: The traffic window: three one-hour exports.
WINDOW_START = datetime(2026, 4, 1, 11, 0, tzinfo=timezone.utc)
HOURS = 3

#: Events per minute, across all services.
EVENTS_PER_MINUTE = 8

#: The deploy that makes checkout slower, and by how much at the median.
DEPLOY_AT = datetime(2026, 4, 1, 12, 30, tzinfo=timezone.utc)
DEPLOY_MEDIAN_SHIFT_MS = 90.0

#: The buffering gateway: everything served in this range is held and then delivered in
#: one catch-up batch, LATE_DELAY after the end of the range.
LATE_RANGE = (
    datetime(2026, 4, 1, 11, 40, tzinfo=timezone.utc),
    datetime(2026, 4, 1, 11, 42, tzinfo=timezone.utc),
)
LATE_DELAY = timedelta(minutes=25)

#: Ordinary delivery: the gateway flushes once a minute, two seconds after the minute
#: closes. Events therefore share a ``received_at`` with the rest of their delivery
#: rather than each having one of their own -- which is what a batching producer
#: actually does, and what makes the rollup's ingest-time watermark advance in steps.
FLUSH_INTERVAL = timedelta(minutes=1)
FLUSH_LAG = timedelta(seconds=2)

#: How many events the 12:00 export repeats from the 11:00 one.
REPEATED_EVENTS = 24

#: (service, route, weight, base latency ms, error rate). Weights pick the route for
#: each event; the quiet introspect route is weighted so it stays small.
ROUTES: list[tuple[str, str, int, float, float]] = [
    ("checkout", "/v1/checkout", 30, 180.0, 0.012),
    ("checkout", "/v1/cart", 20, 95.0, 0.004),
    ("catalog", "/v1/search", 25, 140.0, 0.006),
    ("catalog", "/v1/product", 20, 70.0, 0.002),
    ("auth", "/v1/token", 14, 55.0, 0.003),
    ("auth", "/v1/token/introspect", 1, 40.0, 0.050),
]

REGIONS = ["us-east-1", "us-west-2", "eu-west-1"]
METHODS = {"/v1/checkout": "POST", "/v1/cart": "GET", "/v1/search": "GET",
           "/v1/product": "GET", "/v1/token": "POST", "/v1/token/introspect": "POST"}


def _latency(rng: random.Random, base: float, occurred_at: datetime, service: str) -> float:
    """Draw one latency: lognormal-ish body, occasional fat tail, deploy shift applied."""
    value = base * rng.lognormvariate(0.0, 0.35)
    if rng.random() < 0.02:
        # The tail: a retry, a cold cache, a collection pause.
        value *= rng.uniform(3.0, 8.0)
    if service == "checkout" and occurred_at >= DEPLOY_AT:
        value += DEPLOY_MEDIAN_SHIFT_MS * rng.lognormvariate(0.0, 0.25)
    return round(value, 1)


def _status(rng: random.Random, error_rate: float) -> int:
    """Draw a status code. 4xx happens too, and must not count as our error."""
    roll = rng.random()
    if roll < error_rate:
        return rng.choice([500, 502, 503])
    if roll < error_rate + 0.03:
        return rng.choice([400, 401, 404])
    return 200


def generate(seed: int = SEED) -> list[list[dict]]:
    """Generate one list of event dicts per hourly export.

    Args:
        seed: RNG seed.

    Returns:
        ``HOURS`` lists of events, in time order within each.
    """
    rng = random.Random(seed)
    weights = [route[2] for route in ROUTES]
    exports: list[list[dict]] = [[] for _ in range(HOURS)]
    counter = 0

    for minute in range(HOURS * 60):
        occurred_minute = WINDOW_START + timedelta(minutes=minute)
        hour_index = minute // 60
        for _ in range(EVENTS_PER_MINUTE):
            service, route, _, base, error_rate = rng.choices(ROUTES, weights=weights)[0]
            occurred_at = occurred_minute + timedelta(seconds=rng.uniform(0, 59.999))
            if LATE_RANGE[0] <= occurred_at < LATE_RANGE[1]:
                # One catch-up delivery for the whole buffered window.
                received_at = LATE_RANGE[1] + LATE_DELAY
            else:
                received_at = occurred_minute + FLUSH_INTERVAL + FLUSH_LAG
            counter += 1
            exports[hour_index].append(
                {
                    "event_id": f"evt-{counter:06d}",
                    "service": service,
                    "route": route,
                    "method": METHODS[route],
                    "status_code": _status(rng, error_rate),
                    "latency_ms": _latency(rng, base, occurred_at, service),
                    "region": rng.choice(REGIONS),
                    "occurred_at": occurred_at.isoformat().replace("+00:00", "Z"),
                    "received_at": received_at.isoformat().replace("+00:00", "Z"),
                }
            )

    # The retried delivery: the second export opens with the tail of the first.
    if HOURS > 1 and REPEATED_EVENTS:
        exports[1] = exports[0][-REPEATED_EVENTS:] + exports[1]

    return exports


def export_paths(out: Path) -> Iterator[Path]:
    """Yield the path of each hourly export, in order."""
    for hour in range(HOURS):
        moment = WINDOW_START + timedelta(hours=hour)
        yield out / f"events_{moment:%Y-%m-%dT%H}.jsonl"


def main(argv: list[str] | None = None) -> int:
    """Write the exports and report what was written."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=Path("data"), help="output directory")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    exports = generate(args.seed)
    for path, rows in zip(export_paths(args.out), exports, strict=True):
        path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
        )
        print(f"{path}: {len(rows)} events")
    total = sum(len(rows) for rows in exports)
    unique = len({row["event_id"] for rows in exports for row in rows})
    print(f"total {total} rows, {unique} unique event ids")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
