"""The seasonal baseline.

The scenario most of these tests share is a real one: **last week's incident is in this
week's history.** That is the normal case, not an edge case -- incidents recur, and the
history a baseline is fitted from is whatever actually happened. Whether the detector
still works afterwards is entirely a question of which estimator was used, and the
numbers below make that question arithmetic rather than opinion.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

import pytest

from eventstore.perfmodel.baseline import (
    MIN_BUCKET_OBSERVATIONS,
    SeasonalBaseline,
    hour_of_week,
    scaled_mad,
)

UTC = timezone.utc

#: A Tuesday at 03:00 UTC: weekday 1, hour 3, so hour-of-week 1*24 + 3 = 27.
NOW = datetime(2026, 3, 31, 3, 0, tzinfo=UTC)
BUCKET = 27
#: Half an hour of minute observations, which is the shape of a real incident.
WINDOW_MINUTES = 30


def clean_week(weeks_ago: int) -> list[tuple[datetime, float]]:
    """Thirty ordinary minutes in the same hour-of-week, cycling 99 / 100 / 101."""
    base = NOW - timedelta(weeks=weeks_ago)
    return [(base + timedelta(minutes=i), 100.0 + (i % 3) - 1) for i in range(WINDOW_MINUTES)]


def incident_week(weeks_ago: int, level: float = 300.0) -> list[tuple[datetime, float]]:
    """Thirty minutes at ``level`` in the same hour-of-week: an incident, recorded."""
    base = NOW - timedelta(weeks=weeks_ago)
    return [(base + timedelta(minutes=i), level) for i in range(WINDOW_MINUTES)]


def test_hour_of_week_is_monday_midnight_zero() -> None:
    """Monday 00:00 -> 0, Tuesday 03:00 -> 27, Sunday 23:00 -> 6*24 + 23 = 167."""
    assert hour_of_week(datetime(2026, 3, 30, 0, 0, tzinfo=UTC)) == 0
    assert hour_of_week(NOW) == BUCKET
    assert hour_of_week(datetime(2026, 4, 5, 23, 59, tzinfo=UTC)) == 167


def test_every_hour_of_the_week_has_its_own_bucket() -> None:
    """168 distinct buckets, and none outside the range."""
    start = datetime(2026, 3, 30, 0, 0, tzinfo=UTC)
    seen = {hour_of_week(start + timedelta(hours=h)) for h in range(168)}
    assert seen == set(range(168))


def test_scaled_mad_on_a_textbook_sample() -> None:
    """[1,2,3,4,5]: median 3, deviations [2,1,0,1,2], their median 1, scaled 1.4826."""
    assert scaled_mad([1, 2, 3, 4, 5]) == pytest.approx(1.4826)


def test_scaled_mad_never_returns_zero() -> None:
    """A perfectly constant history would otherwise make every later z infinite."""
    assert scaled_mad([7.0] * 10) > 0.0


def test_the_baseline_is_seasonal_not_global() -> None:
    """Two hours-of-week with very different levels must not be averaged together.

    Tuesday 03:00 sits at 100 and Tuesday 14:00 at 500. A flat baseline would put the
    centre at 300 -- high enough to hide a real 03:00 incident and low enough to page
    somebody every afternoon.
    """
    quiet = clean_week(1)
    busy = [(moment + timedelta(hours=11), value + 400.0) for moment, value in clean_week(1)]
    baseline = SeasonalBaseline.fit(quiet + busy)

    assert baseline.score(NOW, 100.0).expected == 100.0
    assert baseline.score(NOW + timedelta(hours=11), 500.0).expected == 500.0
    assert baseline.score(NOW, 100.0).z_score == pytest.approx(0.0, abs=1e-9)


def test_a_median_and_a_mad_survive_last_weeks_incident() -> None:
    """**The reason this module does not use a mean and a standard deviation.**

    The history is 90 ordinary minutes and the 30 minutes of last week's incident at
    300. A 300ms observation today is scored against that history.

    With a mean and a population standard deviation: mean = 150.0, sd = 86.605427, so
    ``z = (300 - 150) / 86.605427 = 1.731993``. Below every threshold anybody would
    set. Last week's incident has made this week's invisible.

    With a median and a scaled MAD: the 120 sorted values put the median at 100.5 and
    the median absolute deviation at 1.0, scaled to 1.4826, so
    ``z = 199.5 / 1.4826 = 134.5609``. Impossible to miss.

    Both estimators are computed from exactly the same numbers. The difference is
    entirely the breakdown point: a MAD needs half the history to be anomalous before
    it moves, and a standard deviation needs one incident.
    """
    history = clean_week(4) + clean_week(3) + clean_week(2) + incident_week(1)
    values = [value for _, value in history]
    assert len(values) == 120
    assert statistics.mean(values) == 150.0
    assert statistics.pstdev(values) == pytest.approx(86.605427, abs=5e-7)
    assert (300.0 - statistics.mean(values)) / statistics.pstdev(values) == pytest.approx(
        1.731993, abs=5e-7
    )

    score = SeasonalBaseline.fit(history).score(NOW, 300.0)
    assert score.expected == 100.5
    assert score.dispersion == pytest.approx(1.4826, abs=1e-4)
    assert score.z_score == pytest.approx(134.5609, abs=1e-3)
    assert score.z_score > 50.0


def test_fit_excludes_the_window_it_is_asked_to_exclude() -> None:
    """A baseline must not be fitted on the data it is about to score.

    The same 120 observations; excluding last week's incident leaves 90, and moves the
    centre from 100.5 to exactly 100.0. The exclusion range is half-open, so the
    observation at the end boundary survives.
    """
    history = clean_week(4) + clean_week(3) + clean_week(2) + incident_week(1)
    incident_start = NOW - timedelta(weeks=1)
    baseline = SeasonalBaseline.fit(
        history, exclude=(incident_start, incident_start + timedelta(minutes=WINDOW_MINUTES))
    )
    assert baseline.counts[BUCKET] == 90
    assert baseline.centres[BUCKET] == 100.0

    without_exclusion = SeasonalBaseline.fit(history)
    assert without_exclusion.counts[BUCKET] == 120
    assert without_exclusion.centres[BUCKET] == 100.5


def test_a_thin_bucket_falls_back_to_the_pooled_estimate() -> None:
    """Three observations is not a season, and must not be reported as one.

    The bucket at Tuesday 05:00 gets three observations, below
    MIN_BUCKET_OBSERVATIONS, so it is scored against the pooled estimate and says so
    through ``seasonal=False``. The caller can then decide whether to show the score.
    """
    thin_hour = NOW + timedelta(hours=2)
    history = clean_week(2) + [(thin_hour + timedelta(minutes=i), 700.0) for i in range(3)]
    baseline = SeasonalBaseline.fit(history)

    thin = baseline.score(thin_hour, 710.0)
    assert thin.seasonal is False
    assert thin.sample_size == 3
    assert thin.expected == baseline.pooled_centre

    rich = baseline.score(NOW, 100.0)
    assert rich.seasonal is True
    assert rich.sample_size == WINDOW_MINUTES
    assert MIN_BUCKET_OBSERVATIONS == 4


def test_an_unseen_bucket_is_scored_against_the_pool() -> None:
    """Scoring an hour-of-week with no history at all must not raise."""
    baseline = SeasonalBaseline.fit(clean_week(1))
    unseen = baseline.score(NOW + timedelta(hours=5), 100.0)
    assert unseen.seasonal is False
    assert unseen.sample_size == 0


def test_fitting_on_nothing_is_an_error() -> None:
    """Zeros would be indistinguishable from a real baseline of zero."""
    with pytest.raises(ValueError, match="no observations"):
        SeasonalBaseline.fit([])
    with pytest.raises(ValueError, match="no observations"):
        SeasonalBaseline.fit(clean_week(1), exclude=(NOW - timedelta(weeks=2), NOW))


def test_score_as_dict_is_json_ready() -> None:
    payload = SeasonalBaseline.fit(clean_week(1)).score(NOW, 100.0).as_dict()
    assert set(payload) == {
        "value", "expected", "dispersion", "z_score", "bucket", "sample_size", "seasonal",
    }
