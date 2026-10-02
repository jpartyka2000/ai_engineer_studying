"""The committed event exports.

These numbers are exact because ``tools/gen_seed_data.py`` runs with a fixed seed, which
is the only thing that makes an assertion like "1464 rows" honest rather than a snapshot
nobody can derive. If one of them ever has to be changed rather than explained, something
regenerated the data and the right response is to find out what.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

import pytest

from eventstore.ingest import group_by_arrival, parse_batch
from tests.conftest import REPO_ROOT, SEED_DEPLOY_AT, SEED_WINDOW_END, SEED_WINDOW_START, seed_rows

UTC = timezone.utc
#: Rows across the three exports, including the retried delivery.
TOTAL_ROWS = 1464
#: Distinct event ids. The difference from TOTAL_ROWS is the retried batch.
UNIQUE_EVENTS = 1440
#: Events delivered more than two minutes after they happened.
LATE_EVENTS = 16


def test_there_are_three_hourly_exports() -> None:
    paths = sorted((REPO_ROOT / "data").glob("events_*.jsonl"))
    assert [path.name for path in paths] == [
        "events_2026-04-01T11.jsonl",
        "events_2026-04-01T12.jsonl",
        "events_2026-04-01T13.jsonl",
    ]


def test_the_exports_hold_the_expected_rows() -> None:
    rows = seed_rows()
    assert len(rows) == TOTAL_ROWS
    assert len({row["event_id"] for row in rows}) == UNIQUE_EVENTS


def test_the_second_export_repeats_the_tail_of_the_first() -> None:
    """A retried delivery, as a gateway that timed out would send.

    It is in the committed data on purpose: a pipeline is not finished until it has
    been run against a duplicate it did not expect.
    """
    assert TOTAL_ROWS - UNIQUE_EVENTS == 24


def test_every_row_validates() -> None:
    """Including the timestamps, which is the part most likely to rot."""
    parsed = parse_batch(seed_rows())
    assert len(parsed) == TOTAL_ROWS
    assert all(event.occurred_at.tzinfo == UTC for event in parsed)
    assert all(event.received_at is not None for event in parsed)


def test_every_event_is_inside_the_declared_window() -> None:
    parsed = parse_batch(seed_rows())
    assert all(SEED_WINDOW_START <= event.occurred_at < SEED_WINDOW_END for event in parsed)


def test_some_events_arrived_late() -> None:
    """A gateway buffering through a network blip, delivering 25 minutes afterwards.

    Without these the pipeline's late-arrival handling would only ever be exercised by
    a unit test with a hand-built document, and the integration path would be unproven.
    """
    parsed = parse_batch(seed_rows())
    late = [
        event
        for event in parsed
        if event.received_at - event.occurred_at > timedelta(seconds=120)
    ]
    assert len({event.event_id for event in late}) == LATE_EVENTS
    # One catch-up delivery for the whole buffered window, so every late event shares
    # a single received_at and their individual lateness varies with when each was
    # served: between 25 and 27 minutes.
    assert len({event.received_at for event in late}) == 1
    assert all(
        timedelta(minutes=25) <= event.received_at - event.occurred_at <= timedelta(minutes=27)
        for event in late
    )


def test_events_are_delivered_in_batches_not_one_by_one() -> None:
    """A batching producer gives a whole delivery one ingest time.

    It matters because the rollup's watermark advances in ingest time: 179 deliveries
    means 179 watermark positions, not 1464. A generator that stamped every event
    separately would make the inclusive-watermark re-read a single event rather than
    a batch, and the boundary behaviour would never be exercised.
    """
    parsed = parse_batch(seed_rows())
    deliveries = {event.received_at for event in parsed}
    assert len(deliveries) == 179
    assert len(deliveries) < UNIQUE_EVENTS / 5


def test_the_export_replays_as_more_than_one_delivery() -> None:
    """Grouping by arrival must find the late batch as its own delivery."""
    grouped = group_by_arrival(
        parse_batch(seed_rows()), default_received_at=datetime(2026, 4, 2, tzinfo=UTC)
    )
    assert len(grouped) > 1
    assert grouped == sorted(grouped, key=lambda pair: pair[0])


def test_checkout_got_slower_after_the_deploy() -> None:
    """The regression the comparison endpoints exist to find.

    Median latency for ``checkout`` goes from 141.8ms before 12:30 to 228.6ms after:
    a shift of 86.8ms that is real, is worth a rollback, and is invisible in any
    single request, since both windows contain requests at both speeds.
    """
    parsed = {event.event_id: event for event in parse_batch(seed_rows())}.values()
    checkout = [event for event in parsed if event.service == "checkout"]
    before = [e.latency_ms for e in checkout if e.occurred_at < SEED_DEPLOY_AT]
    after = [e.latency_ms for e in checkout if e.occurred_at >= SEED_DEPLOY_AT]

    assert len(before) == 329
    assert len(after) == 315
    assert statistics.median(before) == pytest.approx(141.8)
    assert statistics.median(after) == pytest.approx(228.6)


def test_there_is_a_route_with_a_small_sample() -> None:
    """``/v1/token/introspect`` gets 18 requests in three hours, one of them a 500.

    Any statistic computed over it has an n small enough that a naive confidence
    interval falls over, which is exactly what it is here to demonstrate.
    """
    parsed = {event.event_id: event for event in parse_batch(seed_rows())}.values()
    quiet = [event for event in parsed if event.route == "/v1/token/introspect"]
    assert len(quiet) == 18
    assert sum(1 for event in quiet if event.is_error) == 1


def test_client_errors_are_present_and_are_not_server_errors() -> None:
    """The data contains 4xx responses, so a pipeline that conflates the two is caught."""
    parsed = {event.event_id: event for event in parse_batch(seed_rows())}.values()
    assert any(400 <= event.status_code < 500 for event in parsed)
    assert all(not event.is_error for event in parsed if event.status_code < 500)
