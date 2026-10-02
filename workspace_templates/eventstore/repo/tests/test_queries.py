"""The operational read path, and the indexes it depends on.

The last two tests here are different in kind from the rest. They do not assert what the
query *returns* -- they assert what the server had to *do* to return it. A query that
returns the right hundred documents after examining fifty thousand is correct and is
also an outage waiting for the collection to grow, and the only way to catch that in a
test rather than in production is to read the execution plan.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from eventstore import mongo, queries
from eventstore.config import MAX_RECENT_MINUTES
from eventstore.ingest import ingest_events
from eventstore.models import EventIn

pytestmark = pytest.mark.mongo

UTC = timezone.utc
NOW = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)


def event(event_id: str, **overrides) -> EventIn:
    """Build a valid event, overriding only what a test cares about."""
    payload = {
        "event_id": event_id,
        "service": "checkout",
        "route": "/v1/checkout",
        "method": "POST",
        "status_code": 200,
        "latency_ms": 120.0,
        "region": "us-east-1",
        "occurred_at": NOW - timedelta(minutes=1),
    }
    payload.update(overrides)
    return EventIn.model_validate(payload)


@pytest.fixture
def populated(events):
    """Sixty events for checkout, one per minute going back an hour, plus other noise."""
    batch = [
        event(f"checkout-{n}", occurred_at=NOW - timedelta(minutes=n), latency_ms=100.0 + n)
        for n in range(1, 61)
    ]
    batch += [
        event(f"catalog-{n}", service="catalog", route="/v1/search",
              occurred_at=NOW - timedelta(minutes=n))
        for n in range(1, 11)
    ]
    ingest_events(events, batch)
    return events


def test_recent_window_is_half_open_and_ends_now() -> None:
    start, end = queries.recent_window(15, NOW)
    assert end == NOW
    assert start == NOW - timedelta(minutes=15)


def test_recent_window_is_clamped() -> None:
    """An unbounded range is a query that gets slower every day the service runs."""
    start, _ = queries.recent_window(MAX_RECENT_MINUTES * 10, NOW)
    assert start == NOW - timedelta(minutes=MAX_RECENT_MINUTES)


def test_recent_window_rejects_a_non_positive_span() -> None:
    with pytest.raises(ValueError, match="minutes"):
        queries.recent_window(0, NOW)


def test_recent_events_are_newest_first(populated) -> None:
    found = queries.recent_events(populated, "checkout", minutes=10, limit=100, now=NOW)
    assert [e.event_id for e in found][:3] == ["checkout-1", "checkout-2", "checkout-3"]
    assert found == sorted(found, key=lambda e: e.occurred_at, reverse=True)


def test_recent_events_respect_the_window(populated) -> None:
    """Ten minutes back means ten events, not sixty."""
    assert len(queries.recent_events(populated, "checkout", minutes=10, now=NOW)) == 10
    assert len(queries.recent_events(populated, "checkout", minutes=61, now=NOW)) == 60


def test_recent_events_respect_the_limit(populated) -> None:
    found = queries.recent_events(populated, "checkout", minutes=60, limit=5, now=NOW)
    assert len(found) == 5
    assert found[0].event_id == "checkout-1"


def test_recent_events_are_scoped_to_one_service(populated) -> None:
    found = queries.recent_events(populated, "catalog", minutes=60, limit=100, now=NOW)
    assert {e.service for e in found} == {"catalog"}
    assert len(found) == 10


def test_latency_sample_pools_routes_unless_told_otherwise(populated) -> None:
    window = (NOW - timedelta(minutes=60), NOW)
    pooled = queries.latency_sample(
        populated, service="checkout", start=window[0], end=window[1]
    )
    assert len(pooled) == 60
    scoped = queries.latency_sample(
        populated, service="checkout", route="/v1/cart", start=window[0], end=window[1]
    )
    assert scoped == []


def test_error_counts_exclude_client_errors(events) -> None:
    """Four 200s, two 500s and three 404s: two errors out of nine, not five."""
    ingest_events(
        events,
        [event(f"ok-{n}") for n in range(4)]
        + [event(f"bad-{n}", status_code=500) for n in range(2)]
        + [event(f"client-{n}", status_code=404) for n in range(3)],
    )
    errors, total = queries.error_counts(
        events, service="checkout", start=NOW - timedelta(minutes=10), end=NOW
    )
    assert (errors, total) == (2, 9)


def test_error_counts_on_an_empty_window_are_zero_of_zero(events) -> None:
    """Which the caller must not render as a zero percent error rate."""
    assert queries.error_counts(
        events, service="ghost", start=NOW - timedelta(minutes=10), end=NOW
    ) == (0, 0)


# ---------------------------------------------------------------------------
# What the server actually did
# ---------------------------------------------------------------------------


def test_the_recent_query_is_served_by_the_compound_index(populated) -> None:
    """Equality on ``service`` then a descending range on ``occurred_at``.

    That is exactly the shape of ``service_occurred_at``, so the server walks the
    index and stops at the limit. If this ever reports a different index -- or none --
    the query and the index have stopped matching, and the endpoint has quietly become
    a collection scan that still returns the right answer.
    """
    plan = queries.explain_recent(populated, "checkout", minutes=60, limit=10, now=NOW)
    assert plan["index_name"] == "service_occurred_at"
    assert plan["stage"] != "COLLSCAN"


def test_the_recent_query_does_not_sort_in_memory(populated) -> None:
    """The sort must come from the index, not from a SORT stage.

    A SORT stage means the server materialised every matching document and ordered
    them before applying the limit. On sixty events that is invisible; on a day of
    production traffic it is the difference between reading a hundred documents and
    reading fifty thousand. No index name on its own shows this -- the query can
    still *use* ``service_occurred_at`` for the filter and then sort what it found.
    """
    plan = queries.explain_recent(populated, "checkout", minutes=60, limit=10, now=NOW)
    assert plan["sort_in_memory"] == 0


def test_the_recent_query_examines_about_what_it_returns(populated) -> None:
    """Ten documents returned, and the server should not have looked at many more.

    A sort the index cannot satisfy would force the server to fetch every event in the
    window before ordering them -- sixty here, and sixty thousand in production -- so
    the ratio, not the absolute count, is the thing being pinned.
    """
    plan = queries.explain_recent(populated, "checkout", minutes=60, limit=10, now=NOW)
    assert plan["docs_returned"] == 10
    assert plan["docs_examined"] <= 20


def test_the_seed_script_and_the_code_declare_the_same_indexes() -> None:
    """``seed/001_indexes.js`` runs only on an empty volume, so the code is the
    authority -- but an environment created from the script and one created by the
    application must not end up with different indexes."""
    from pathlib import Path

    script = (Path(__file__).resolve().parents[1] / "seed" / "001_indexes.js").read_text()
    for spec in mongo.INDEX_SPECS:
        assert f'name: "{spec["name"]}"' in script, f"{spec['name']} missing from seed script"
    assert script.count("createIndex") == len(mongo.INDEX_SPECS)
