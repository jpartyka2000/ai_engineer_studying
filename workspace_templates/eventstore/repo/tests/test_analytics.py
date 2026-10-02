"""The warehouse-backed analytics.

These tests need DuckDB but not MongoDB: ``insert_facts`` writes ``fact_requests``
directly and rebuilds the affected rollups, which is the same code path the rollup job
uses once the events have been copied across. That split is deliberate -- a question
about a statistic should not require a running database server to answer.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

import pytest

from eventstore import analytics
from eventstore.perfmodel.intervals import Interval
from tests.conftest import fact, insert_facts

UTC = timezone.utc
START = datetime(2026, 4, 1, 11, 0, tzinfo=UTC)
HOUR = START + timedelta(hours=1)


def ramp(connection, *, service="checkout", route="/v1/checkout", minute=0, latencies, status=200):
    """Insert one latency per event into a single minute bucket."""
    moment = START + timedelta(minutes=minute)
    rows = [
        fact(
            f"{service}-{minute}-{index}",
            service=service,
            route=route,
            latency_ms=latency,
            status_code=status,
            occurred_at=moment + timedelta(seconds=index % 60),
        )
        for index, latency in enumerate(latencies)
    ]
    insert_facts(connection, rows)


# ---------------------------------------------------------------------------
# latency_profile
# ---------------------------------------------------------------------------


def test_latency_profile_reports_percentiles_apdex_and_a_median_interval(warehouse) -> None:
    """100 requests at 1..100 ms against the default 300ms Apdex target.

    p50 = 50, p95 = 95, p99 = 99. Every request is under the target, so Apdex is 1.0.
    The median interval must bracket the sample median of 50.
    """
    ramp(warehouse, latencies=[float(n) for n in range(1, 101)])
    profile = analytics.latency_profile(
        warehouse, service="checkout", route=None, start=START, end=HOUR, seed=7
    )
    assert profile.summary.p50 == 50.0
    assert profile.summary.p95 == 95.0
    assert profile.summary.p99 == 99.0
    assert profile.satisfaction.score == 1.0
    assert profile.median_ci.contains(50.0)


def test_latency_profile_is_reproducible(warehouse) -> None:
    """Same window, same seed, same interval -- including the bootstrapped part."""
    ramp(warehouse, latencies=[float(n) for n in range(1, 60)])
    kwargs = dict(service="checkout", route=None, start=START, end=HOUR, seed=99)
    first = analytics.latency_profile(warehouse, **kwargs)
    second = analytics.latency_profile(warehouse, **kwargs)
    assert first.median_ci == second.median_ci


def test_latency_profile_filters_by_route(warehouse) -> None:
    ramp(warehouse, route="/v1/checkout", latencies=[10.0] * 5)
    ramp(warehouse, route="/v1/cart", minute=1, latencies=[900.0] * 5)
    profile = analytics.latency_profile(
        warehouse, service="checkout", route="/v1/checkout", start=START, end=HOUR, seed=1
    )
    assert profile.summary.count == 5
    assert profile.summary.max == 10.0


def test_an_empty_window_is_an_error_not_a_zero(warehouse) -> None:
    """"No traffic" and "instant responses" must not render the same."""
    with pytest.raises(ValueError, match="no requests"):
        analytics.latency_profile(
            warehouse, service="ghost", route=None, start=START, end=HOUR, seed=1
        )


# ---------------------------------------------------------------------------
# error_rate
# ---------------------------------------------------------------------------


def test_error_rate_reads_the_rollups_and_carries_an_interval(warehouse) -> None:
    """17 requests of which 1 is a 500.

    rate = 1/17 = 0.058824, and the Wilson interval must contain it while reaching
    nowhere near zero width -- one error in seventeen requests is not a measurement
    of anything precise.
    """
    ramp(warehouse, latencies=[100.0] * 16)
    ramp(warehouse, minute=1, latencies=[100.0], status=503)
    rate = analytics.error_rate(warehouse, service="checkout", start=START, end=HOUR)
    assert (rate.errors, rate.total) == (1, 17)
    assert rate.rate == pytest.approx(1 / 17)
    assert rate.interval.contains(1 / 17)
    assert rate.interval.width > 0.1


def test_a_clean_but_tiny_sample_does_not_report_certainty(warehouse) -> None:
    """Five requests, no errors. The rate is 0.0 and the upper bound is 0.434482.

    A naive proportion would report "0% errors" and an interval of zero width, which
    is the single most common way a small sample is misread.
    """
    ramp(warehouse, latencies=[100.0] * 5)
    rate = analytics.error_rate(warehouse, service="checkout", start=START, end=HOUR)
    assert rate.rate == 0.0
    assert rate.interval.low == 0.0
    assert rate.interval.high == pytest.approx(0.434482, abs=5e-7)


def test_client_errors_are_not_our_errors(warehouse) -> None:
    ramp(warehouse, latencies=[100.0] * 4, status=404)
    rate = analytics.error_rate(warehouse, service="checkout", start=START, end=HOUR)
    assert (rate.errors, rate.total) == (0, 4)


def test_an_empty_window_reports_total_ignorance(warehouse) -> None:
    """Zero of zero: the interval is [0, 1], which is the honest answer."""
    rate = analytics.error_rate(warehouse, service="ghost", start=START, end=HOUR)
    assert (rate.errors, rate.total) == (0, 0)
    assert rate.interval == Interval(0.0, 1.0)


# ---------------------------------------------------------------------------
# compare_windows
# ---------------------------------------------------------------------------

#: A deploy that added about 90ms to the middle of the distribution.
BASELINE_SAMPLE = [100.0 + n for n in range(0, 60, 2)]
CANDIDATE_SAMPLE = [190.0 + n for n in range(0, 60, 2)]


def test_a_slower_release_is_detected() -> None:
    """Complete separation: every candidate request is slower than every baseline one.

    U is therefore the maximum, the effect size is +1.0, and the bootstrapped median
    shift must be strictly positive at its lower bound -- which is what
    ``regressed`` requires before it will say yes.
    """
    result = analytics.compare_windows(CANDIDATE_SAMPLE, BASELINE_SAMPLE, seed=3)
    assert result.comparison.effect_size == 1.0
    assert result.median_shift_ms == pytest.approx(90.0)
    assert result.shift_ci.low > 0
    assert result.regressed is True


def test_an_unchanged_release_is_not_a_regression() -> None:
    """The same sample compared with itself: effect size 0, shift 0, not a regression."""
    result = analytics.compare_windows(BASELINE_SAMPLE, BASELINE_SAMPLE, seed=3)
    assert result.comparison.effect_size == pytest.approx(0.0)
    assert result.median_shift_ms == 0.0
    assert result.regressed is False


def test_a_faster_release_is_not_a_regression() -> None:
    result = analytics.compare_windows(BASELINE_SAMPLE, CANDIDATE_SAMPLE, seed=3)
    assert result.comparison.effect_size == -1.0
    assert result.regressed is False


def test_a_tiny_sample_cannot_declare_a_regression() -> None:
    """Three requests against three. The effect size is real; the p-value is not.

    ``regressed`` requires ``approximation_valid``, so a canary with six requests in
    it cannot trigger a rollback however separated the two samples look.
    """
    result = analytics.compare_windows([300.0, 310.0, 320.0], [100.0, 110.0, 120.0], seed=3)
    assert result.comparison.effect_size == 1.0
    assert result.comparison.approximation_valid is False
    assert result.regressed is False


def test_comparison_needs_both_windows() -> None:
    with pytest.raises(ValueError, match="both windows"):
        analytics.compare_windows([], BASELINE_SAMPLE, seed=1)


def test_comparison_is_reproducible() -> None:
    first = analytics.compare_windows(CANDIDATE_SAMPLE, BASELINE_SAMPLE, seed=42)
    second = analytics.compare_windows(CANDIDATE_SAMPLE, BASELINE_SAMPLE, seed=42)
    assert first.shift_ci == second.shift_ci


# ---------------------------------------------------------------------------
# detect_sustained_regression
# ---------------------------------------------------------------------------

#: Thirty minutes alternating 90/110: median exactly 100, population sd exactly 10.
REFERENCE_PATTERN = [90.0, 110.0] * 15
#: Thirty minutes alternating 100/120: the same spread, shifted up by exactly one sigma.
SHIFTED_PATTERN = [100.0, 120.0] * 15


def series_of(values: list[float]) -> list[tuple[datetime, float]]:
    """Attach consecutive minute timestamps to a list of values."""
    return [(START + timedelta(minutes=index), value) for index, value in enumerate(values)]


def test_a_one_sigma_sustained_shift_is_detected() -> None:
    """**The deploy-verification test.**

    The reference period fixes target = 100 and sigma = 10 exactly. Every point after
    index 30 is drawn from a distribution shifted up by one sigma -- a regression that
    no individual minute reveals, since 100 and 120 both occurred before the deploy
    too.

    The CUSUM statistic accumulates 1.5 on each high point and sheds 0.5 on each low
    one, so it climbs 1.0 per pair and first exceeds h = 5 at **index 39**, where it
    is exactly 5.5. Ten minutes after the deploy.

    An EWMA chart on this series never alarms at all: its weighted mean converges to
    110, a deviation of one sigma, against a control band of 12.6025. That is the
    whole reason this function calls CUSUM.
    """
    result = analytics.detect_sustained_regression(
        series_of(REFERENCE_PATTERN + SHIFTED_PATTERN), reference_points=30
    )
    assert result.alarmed is True
    assert result.index == 39
    assert result.statistic[39] == pytest.approx(5.5)


def test_a_stable_service_does_not_alarm() -> None:
    """Sixty minutes of the same oscillation. A detector that fires here is noise."""
    result = analytics.detect_sustained_regression(
        series_of(REFERENCE_PATTERN * 2), reference_points=30
    )
    assert result.alarmed is False
    assert result.index is None


def test_the_reference_period_defines_target_and_sigma() -> None:
    """Stated as an assertion because the rest of the arithmetic depends on it."""
    assert statistics.median(REFERENCE_PATTERN) == 100.0
    assert statistics.pstdev(REFERENCE_PATTERN) == 10.0


def test_detection_needs_more_points_than_its_reference() -> None:
    with pytest.raises(ValueError, match="need more than"):
        analytics.detect_sustained_regression(series_of([100.0] * 10), reference_points=10)
    with pytest.raises(ValueError, match="reference_points"):
        analytics.detect_sustained_regression(series_of([100.0] * 10), reference_points=1)


# ---------------------------------------------------------------------------
# minute_series and anomaly_scan
# ---------------------------------------------------------------------------


def test_minute_series_returns_buckets_in_time_order(warehouse) -> None:
    ramp(warehouse, minute=2, latencies=[300.0] * 4)
    ramp(warehouse, minute=0, latencies=[100.0] * 4)
    ramp(warehouse, minute=1, latencies=[200.0] * 4)
    series = analytics.minute_series(
        warehouse, service="checkout", route=None, start=START, end=HOUR
    )
    assert [value for _, value in series] == [100.0, 200.0, 300.0]
    assert [moment for moment, _ in series] == [
        START, START + timedelta(minutes=1), START + timedelta(minutes=2)
    ]
    assert all(moment.tzinfo is not None for moment, _ in series)


def test_minute_series_rejects_an_unknown_column(warehouse) -> None:
    """The column is interpolated into SQL, so the whitelist is load-bearing."""
    with pytest.raises(ValueError, match="unknown rollup column"):
        analytics.minute_series(
            warehouse, service="checkout", route=None, start=START, end=HOUR,
            column="1; DROP TABLE fact_requests",
        )


#: Three prior weeks, not four: ``anomaly_scan`` fits on the 28 days *ending at* the
#: window's end, so a point exactly 28 days before the window's start falls outside it.
HISTORY_WEEKS = (1, 2, 3)
#: Alternating p95 values, so the bucket's MAD is a real number rather than the floor.
#: Each minute's four requests give p95 = rank ceil(0.95*4) = 4, i.e. the maximum.
QUIET_MINUTES = ([100.0, 110.0, 90.0, 100.0], [100.0, 120.0, 90.0, 100.0])


def test_anomaly_scan_scores_every_minute_of_the_window(warehouse) -> None:
    """Ten quiet minutes and then one bad one, scored against three weeks of history.

    Each history minute has p95 of 110 or 120, so the bucket's median is 115 and its
    scaled MAD is 1.4826 * 5 = 7.413. A quiet minute therefore scores |z| = 0.675 and
    the bad minute, at p95 = 910, scores (910 - 115) / 7.413 = 107.
    """
    for week in HISTORY_WEEKS:
        base_minute = -week * 7 * 24 * 60
        for offset in range(10):
            ramp(warehouse, minute=base_minute + offset, latencies=QUIET_MINUTES[offset % 2])
    for offset in range(10):
        ramp(warehouse, minute=offset, latencies=QUIET_MINUTES[offset % 2])
    ramp(warehouse, minute=10, latencies=[900.0, 910.0, 890.0, 900.0])

    scores = analytics.anomaly_scan(
        warehouse, service="checkout", start=START, end=START + timedelta(minutes=11)
    )
    assert len(scores) == 11
    assert scores[0].expected == 115.0
    assert scores[0].dispersion == pytest.approx(7.413, abs=1e-3)
    assert scores[-1].value == 910.0
    assert scores[-1].z_score > 10.0
    assert all(abs(score.z_score) < 3.0 for score in scores[:-1])


def test_anomaly_scan_excludes_the_window_it_scores(warehouse) -> None:
    """The baseline must not be fitted on the data it is about to judge.

    Here the window is the only history in its bucket apart from four prior weeks, so
    the exclusion shows up directly in the fitted sample size rather than in the
    score: the baseline sees the prior weeks only.
    """
    for week in HISTORY_WEEKS:
        base_minute = -week * 7 * 24 * 60
        for offset in range(5):
            ramp(warehouse, minute=base_minute + offset, latencies=[100.0] * 4)
    for offset in range(5):
        ramp(warehouse, minute=offset, latencies=[500.0] * 4)

    scores = analytics.anomaly_scan(
        warehouse, service="checkout", start=START, end=START + timedelta(minutes=5)
    )
    assert len(scores) == 5
    # 3 weeks x 5 minutes of history in this hour-of-week bucket, and not the 5
    # minutes being scored. Had the window been included the centre would be 300.
    assert scores[0].sample_size == 15
    assert scores[0].expected == 100.0


def test_anomaly_scan_needs_history(warehouse) -> None:
    ramp(warehouse, latencies=[100.0] * 4)
    with pytest.raises(ValueError, match="no observations"):
        analytics.anomaly_scan(
            warehouse, service="checkout", start=START, end=START + timedelta(minutes=1)
        )
