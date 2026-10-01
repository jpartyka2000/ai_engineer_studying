"""Watermarks: forward only, and only over work that finished.

Both failure modes this file guards against are silent in production and look identical --
a day with less data than expected. A regressing watermark re-reads a window; a watermark
that advanced over failed work skips one forever, and keeps skipping it, because from then on
the pipeline is consistently looking past it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from etlduck.bronze import ingest_all
from etlduck.gold import build_gold
from etlduck.pipeline import USAGE_STREAM, run_pipeline
from etlduck.quality import QualityFailure
from etlduck.silver import build_silver
from etlduck.watermark import (
    EPOCH,
    WatermarkRegression,
    advance_watermark,
    get_watermark,
    max_event_time,
    watermark_advanced_on_success,
)
from tests.conftest import event, write_accounts, write_usage

T1 = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)
ACCOUNTS = [
    {"account_id": f"acct-{n:03d}", "name": f"A{n}", "plan": "team", "country": "DE"}
    for n in range(6)
]


# ---------------------------------------------------------------------------
# Reading and writing
# ---------------------------------------------------------------------------


def test_an_unknown_stream_starts_at_the_epoch(connection):
    """Returned rather than None so every caller can compare without a special case."""
    assert get_watermark(connection, "never-run") == EPOCH


def test_a_watermark_round_trips_as_utc(connection):
    advance_watermark(connection, USAGE_STREAM, T1)
    stored = get_watermark(connection, USAGE_STREAM)
    assert stored == T1
    assert stored.tzinfo is not None


def test_a_watermark_moves_forward(connection):
    advance_watermark(connection, USAGE_STREAM, T1)
    advance_watermark(connection, USAGE_STREAM, T2)
    assert get_watermark(connection, USAGE_STREAM) == T2


def test_advancing_to_the_same_position_is_allowed(connection):
    """A run that found no new events is not an error, and must not raise."""
    advance_watermark(connection, USAGE_STREAM, T1)
    advance_watermark(connection, USAGE_STREAM, T1)
    assert get_watermark(connection, USAGE_STREAM) == T1


def test_streams_are_independent(connection):
    advance_watermark(connection, "usage", T2)
    advance_watermark(connection, "billing", T1)
    assert get_watermark(connection, "usage") == T2
    assert get_watermark(connection, "billing") == T1


# ---------------------------------------------------------------------------
# Refusing to regress
# ---------------------------------------------------------------------------


def test_moving_a_watermark_backwards_raises(connection):
    """Raised rather than clamped. A caller computing an earlier position has a bug, and
    silently keeping the old value hides it until someone asks why a backfill did nothing."""
    advance_watermark(connection, USAGE_STREAM, T2)
    with pytest.raises(WatermarkRegression, match="refusing to move the watermark"):
        advance_watermark(connection, USAGE_STREAM, T1)
    assert get_watermark(connection, USAGE_STREAM) == T2


def test_a_failed_regression_leaves_the_watermark_untouched(connection):
    advance_watermark(connection, USAGE_STREAM, T2)
    with pytest.raises(WatermarkRegression):
        advance_watermark(connection, USAGE_STREAM, T2 - timedelta(seconds=1))
    assert get_watermark(connection, USAGE_STREAM) == T2


def test_a_naive_position_is_rejected(connection):
    """A watermark compared against an instant in another zone is worse than none at all."""
    with pytest.raises(ValueError, match="timezone-aware"):
        advance_watermark(connection, USAGE_STREAM, datetime(2026, 3, 1, 12, 0))


def test_a_position_in_another_zone_is_normalised_before_comparison(connection):
    """19:00-05:00 is 00:00 the next day in UTC, so this is forward motion, not a regression."""
    advance_watermark(connection, USAGE_STREAM, T1)
    local = datetime(2026, 3, 1, 19, 0, tzinfo=timezone(timedelta(hours=-5)))
    advance_watermark(connection, USAGE_STREAM, local)
    assert get_watermark(connection, USAGE_STREAM) == datetime(
        2026, 3, 2, 0, 0, tzinfo=timezone.utc
    )


# ---------------------------------------------------------------------------
# Only on success
# ---------------------------------------------------------------------------


def test_the_watermark_advances_after_successful_work(connection):
    with watermark_advanced_on_success(connection, USAGE_STREAM, T1):
        pass
    assert get_watermark(connection, USAGE_STREAM) == T1


def test_the_watermark_does_not_advance_when_the_work_raises(connection):
    """The ordering inside the context manager is the whole point: the body runs first."""

    class Boom(RuntimeError):
        pass

    with pytest.raises(Boom):
        with watermark_advanced_on_success(connection, USAGE_STREAM, T1):
            raise Boom("the job died halfway through")

    assert get_watermark(connection, USAGE_STREAM) == EPOCH


# ---------------------------------------------------------------------------
# Deriving the position
# ---------------------------------------------------------------------------


def test_max_event_time_is_the_epoch_on_an_empty_warehouse(connection):
    assert max_event_time(connection) == EPOCH


def test_max_event_time_reads_the_newest_event_not_the_clock(connection, root):
    """Usage telemetry arrives late as a matter of course, so a watermark set to "now" skips
    whatever is still in flight. The newest event actually processed is the only safe position."""
    write_accounts(root, "accounts.csv", ACCOUNTS)
    write_usage(
        root,
        "usage_events_2026-03-01.jsonl",
        [
            event("e1", occurred_at="2026-03-01T08:00:00+00:00"),
            event("e2", occurred_at="2026-03-01T21:45:00+00:00"),
            event("e3", occurred_at="2026-03-01T13:00:00+00:00"),
        ],
    )
    ingest_all(connection, root)
    build_silver(connection)
    assert max_event_time(connection) == datetime(2026, 3, 1, 21, 45, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Inside the pipeline
# ---------------------------------------------------------------------------


def test_a_successful_run_advances_the_watermark(connection, root):
    write_accounts(root, "accounts.csv", ACCOUNTS)
    write_usage(
        root,
        "usage_events_2026-03-01.jsonl",
        [event("e1", occurred_at="2026-03-01T15:00:00+00:00")],
    )
    result = run_pipeline(connection, root)
    assert result.ok
    assert get_watermark(connection, USAGE_STREAM) == datetime(
        2026, 3, 1, 15, 0, tzinfo=timezone.utc
    )


def test_a_run_that_fails_its_quality_gates_does_not_advance_the_watermark(connection, root):
    """The gate protects the watermark, not the other way round. Only four accounts are
    delivered, which trips ``accounts_present``; the batch must stay unprocessed so a later
    run with the full dimension picks it up.
    """
    write_accounts(root, "accounts.csv", ACCOUNTS[:4])
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("e1", "acct-000")])

    with pytest.raises(QualityFailure, match="accounts_present"):
        run_pipeline(connection, root)

    assert get_watermark(connection, USAGE_STREAM) == EPOCH


def test_a_non_strict_run_still_refuses_to_advance(connection, root):
    """``strict=False`` changes whether the run shouts, never whether the watermark moves.
    The flag exists for inspecting a broken warehouse, not for getting past the gate."""
    write_accounts(root, "accounts.csv", ACCOUNTS[:4])
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("e1", "acct-000")])

    result = run_pipeline(connection, root, strict=False)
    assert not result.ok
    assert get_watermark(connection, USAGE_STREAM) == EPOCH


def test_rerunning_a_successful_pipeline_does_not_regress_the_watermark(connection, root):
    """Gold and silver are rebuilt from scratch every run, so the watermark is recomputed
    every run too. Recomputing the same value must not look like a regression."""
    write_accounts(root, "accounts.csv", ACCOUNTS)
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("e1")])
    run_pipeline(connection, root)
    first = get_watermark(connection, USAGE_STREAM)
    run_pipeline(connection, root)
    assert get_watermark(connection, USAGE_STREAM) == first


def test_the_committed_run_advances_past_the_last_event(seeded):
    connection, _ = seeded
    assert get_watermark(connection, USAGE_STREAM) == max_event_time(connection)
    assert get_watermark(connection, USAGE_STREAM) > datetime(2026, 3, 2, tzinfo=timezone.utc)


def test_gold_does_not_touch_the_watermark(connection, root):
    """Separation of concerns, pinned: only the pipeline runner owns the watermark, so a
    layer rebuilt on its own cannot mark work as done."""
    write_accounts(root, "accounts.csv", ACCOUNTS)
    write_usage(root, "usage_events_2026-03-01.jsonl", [event("e1")])
    ingest_all(connection, root)
    build_silver(connection)
    build_gold(connection)
    assert get_watermark(connection, USAGE_STREAM) == EPOCH
