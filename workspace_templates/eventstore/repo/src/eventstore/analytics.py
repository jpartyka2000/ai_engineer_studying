"""The questions the dashboards ask, answered from the warehouse.

This module is the seam between the two halves of the service. Below it,
:mod:`eventstore.perfmodel` knows statistics and nothing else; beside it,
:mod:`eventstore.duck` knows storage and nothing else. Here is where a question like
"is the 14:05 deploy slower than the one before it" turns into a window, a query and a
statistic.

**Every function takes its window explicitly.** None of them call ``utcnow()``. A
report that silently means "the last hour, as of whenever you happened to run it" cannot
be reproduced, compared with yesterday's, or asserted in a test.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence

import duckdb

from eventstore.config import APDEX_TARGET_MS
from eventstore.perfmodel.apdex import ApdexScore, apdex
from eventstore.perfmodel.baseline import AnomalyScore, SeasonalBaseline
from eventstore.perfmodel.changepoint import DetectionResult, cusum_detect
from eventstore.perfmodel.intervals import Interval, bootstrap_ci, wilson_interval
from eventstore.perfmodel.nonparametric import ComparisonResult, mann_whitney_u
from eventstore.perfmodel.percentiles import LatencySummary, summarize

#: How much history the anomaly scan fits a baseline from. Two weeks gives each
#: hour-of-week bucket two observations at minimum, which is below
#: MIN_BUCKET_OBSERVATIONS -- deliberately, so that a thin history falls back to the
#: pooled estimate rather than pretending to be seasonal.
DEFAULT_BASELINE_DAYS = 28

#: Resamples used for every bootstrap interval the service reports. Enough that the
#: interval is stable to the millisecond at the sample sizes seen here.
DEFAULT_RESAMPLES = 2000


def _naive(moment: datetime) -> datetime:
    """Return a timezone-aware datetime as naive UTC, for DuckDB parameters."""
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


def _aware(moment: datetime) -> datetime:
    """Return a naive warehouse timestamp as timezone-aware UTC."""
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment


def latencies_in_window(
    connection: duckdb.DuckDBPyConnection,
    *,
    service: str,
    route: str | None,
    start: datetime,
    end: datetime,
) -> list[float]:
    """Return raw latencies from ``fact_requests`` for a window.

    Args:
        connection: An open warehouse connection.
        service: Exact service name.
        route: Exact route, or ``None`` to pool every route.
        start: Window start, inclusive.
        end: Window end, exclusive.

    Returns:
        Latencies in milliseconds.
    """
    criteria = "service = ? AND occurred_at >= ? AND occurred_at < ?"
    params: list[object] = [service, _naive(start), _naive(end)]
    if route is not None:
        criteria += " AND route = ?"
        params.append(route)
    rows = connection.execute(
        f"SELECT latency_ms FROM fact_requests WHERE {criteria}", params  # noqa: S608
    ).fetchall()
    return [float(row[0]) for row in rows]


@dataclass(frozen=True)
class LatencyProfile:
    """Percentiles and Apdex for one window.

    Attributes:
        summary: Nearest-rank percentiles over the window.
        satisfaction: Apdex against the configured target.
        median_ci: Bootstrap interval for the median, so a p50 computed from eleven
            requests is visibly less certain than one computed from eleven thousand.
    """

    summary: LatencySummary
    satisfaction: ApdexScore
    median_ci: Interval

    def as_dict(self) -> dict[str, object]:
        """Return the profile as a JSON-serialisable dict."""
        return {
            "latency": self.summary.as_dict(),
            "apdex": self.satisfaction.as_dict(),
            "median_ci": self.median_ci.as_dict(),
        }


def latency_profile(
    connection: duckdb.DuckDBPyConnection,
    *,
    service: str,
    route: str | None,
    start: datetime,
    end: datetime,
    target_ms: float = APDEX_TARGET_MS,
    seed: int,
) -> LatencyProfile:
    """Profile a window's latency.

    Args:
        connection: An open warehouse connection.
        service: Exact service name.
        route: Exact route, or ``None``.
        start: Window start, inclusive.
        end: Window end, exclusive.
        target_ms: Apdex target.
        seed: Bootstrap seed, so two requests for the same window agree.

    Returns:
        A :class:`LatencyProfile`.

    Raises:
        ValueError: If the window holds no requests.
    """
    sample = latencies_in_window(
        connection, service=service, route=route, start=start, end=end
    )
    if not sample:
        raise ValueError(f"no requests for {service!r} between {start} and {end}")
    return LatencyProfile(
        summary=summarize(sample),
        satisfaction=apdex(sample, target_ms),
        median_ci=bootstrap_ci(
            sample, statistics.median, seed=seed, resamples=DEFAULT_RESAMPLES
        ),
    )


@dataclass(frozen=True)
class ErrorRate:
    """An error rate with the interval that says how much to believe it.

    Attributes:
        errors: 5xx responses in the window.
        total: Requests in the window.
        rate: ``errors / total``, or 0.0 for an empty window.
        interval: Wilson score interval for the true rate.
    """

    errors: int
    total: int
    rate: float
    interval: Interval

    def as_dict(self) -> dict[str, object]:
        """Return the rate as a JSON-serialisable dict."""
        return {
            "errors": self.errors,
            "total": self.total,
            "rate": self.rate,
            "interval": self.interval.as_dict(),
        }


def error_rate(
    connection: duckdb.DuckDBPyConnection,
    *,
    service: str,
    start: datetime,
    end: datetime,
) -> ErrorRate:
    """Compute a service's error rate over a window, with a Wilson interval.

    Read from ``rollup_minute`` rather than ``fact_requests``: the counts are already
    aggregated there, and an error-rate panel covering a month must not scan a month
    of individual requests.

    Args:
        connection: An open warehouse connection.
        service: Exact service name.
        start: Window start, inclusive.
        end: Window end, exclusive.

    Returns:
        An :class:`ErrorRate`.
    """
    row = connection.execute(
        """
        SELECT coalesce(sum(errors), 0), coalesce(sum(requests), 0)
        FROM rollup_minute
        WHERE service = ? AND bucket >= ? AND bucket < ?
        """,
        [service, _naive(start), _naive(end)],
    ).fetchone()
    errors, total = int(row[0]), int(row[1])
    return ErrorRate(
        errors=errors,
        total=total,
        rate=0.0 if total == 0 else errors / total,
        interval=wilson_interval(errors, total),
    )


@dataclass(frozen=True)
class ReleaseComparison:
    """Whether one window is slower than another.

    Attributes:
        comparison: The Mann-Whitney result. ``effect_size > 0`` means the candidate
            window is slower.
        median_shift_ms: Candidate median minus baseline median.
        shift_ci: Bootstrap interval for that shift. An interval straddling zero is
            the result that should stop a rollback, whatever the p-value says.
        candidate: Percentiles for the candidate window.
        baseline: Percentiles for the baseline window.
    """

    comparison: ComparisonResult
    median_shift_ms: float
    shift_ci: Interval
    candidate: LatencySummary
    baseline: LatencySummary

    @property
    def regressed(self) -> bool:
        """Whether the candidate is slower on both the test and the interval.

        Both, because either alone is misleading: with enough traffic a 1ms shift is
        significant, and with little traffic a real regression is not.
        """
        return (
            self.comparison.approximation_valid
            and self.comparison.p_value < 0.05
            and self.comparison.effect_size > 0
            and self.shift_ci.low > 0
        )

    def as_dict(self) -> dict[str, object]:
        """Return the comparison as a JSON-serialisable dict."""
        return {
            "comparison": self.comparison.as_dict(),
            "median_shift_ms": self.median_shift_ms,
            "shift_ci": self.shift_ci.as_dict(),
            "candidate": self.candidate.as_dict(),
            "baseline": self.baseline.as_dict(),
            "regressed": self.regressed,
        }


def compare_windows(
    candidate: Sequence[float],
    baseline: Sequence[float],
    *,
    seed: int,
    resamples: int = DEFAULT_RESAMPLES,
) -> ReleaseComparison:
    """Compare two latency samples.

    Args:
        candidate: Latencies from the window under test.
        baseline: Latencies from the reference window.
        seed: Bootstrap seed.
        resamples: Bootstrap resamples.

    Returns:
        A :class:`ReleaseComparison`.

    Raises:
        ValueError: If either sample is empty.
    """
    if not candidate or not baseline:
        raise ValueError("both windows must contain requests")

    baseline_median = statistics.median(baseline)
    # The shift is bootstrapped by resampling the candidate against a fixed baseline
    # median. Resampling both and subtracting would widen the interval by the
    # baseline's own uncertainty, which is not what "how much slower is the new one"
    # asks.
    shift_ci = bootstrap_ci(
        candidate,
        lambda sample: statistics.median(sample) - baseline_median,
        seed=seed,
        resamples=resamples,
    )
    return ReleaseComparison(
        comparison=mann_whitney_u(candidate, baseline),
        median_shift_ms=statistics.median(candidate) - baseline_median,
        shift_ci=shift_ci,
        candidate=summarize(candidate),
        baseline=summarize(baseline),
    )


def minute_series(
    connection: duckdb.DuckDBPyConnection,
    *,
    service: str,
    route: str | None,
    start: datetime,
    end: datetime,
    column: str = "p95_ms",
) -> list[tuple[datetime, float]]:
    """Return a per-minute series from ``rollup_minute``.

    Args:
        connection: An open warehouse connection.
        service: Exact service name.
        route: Exact route, or ``None`` to average across routes weighted by requests.
        start: Window start, inclusive.
        end: Window end, exclusive.
        column: Which rollup column to read. Must be one of the known numeric
            columns; it is interpolated into SQL and is checked against a whitelist.

    Returns:
        ``(bucket, value)`` pairs in time order, with timezone-aware buckets.

    Raises:
        ValueError: If ``column`` is not a known rollup column.
    """
    allowed = {"p50_ms", "p95_ms", "p99_ms", "max_latency_ms", "requests", "errors"}
    if column not in allowed:
        raise ValueError(f"unknown rollup column {column!r}; expected one of {sorted(allowed)}")

    criteria = "service = ? AND bucket >= ? AND bucket < ?"
    params: list[object] = [service, _naive(start), _naive(end)]
    if route is not None:
        criteria += " AND route = ?"
        params.append(route)

    rows = connection.execute(
        f"""
        SELECT bucket, max({column}) AS value
        FROM rollup_minute
        WHERE {criteria}
        GROUP BY bucket
        ORDER BY bucket
        """,  # noqa: S608 - column is whitelisted above
        params,
    ).fetchall()
    return [(_aware(row[0]), float(row[1])) for row in rows]


def detect_sustained_regression(
    series: Sequence[tuple[datetime, float]],
    *,
    reference_points: int,
) -> DetectionResult:
    """Detect a sustained shift in a per-minute series with CUSUM.

    CUSUM, not EWMA. A deploy regression is a small permanent shift, and the whole
    point of accumulating deviations is to catch one that no single observation makes
    obvious. See :mod:`eventstore.perfmodel.changepoint`.

    Args:
        series: ``(bucket, value)`` pairs in time order.
        reference_points: How many leading points define the in-control state. These
            points are both the reference and part of the monitored series, which is
            conventional for a control chart: the chart is expected not to alarm on
            its own reference period.

    Returns:
        A :class:`~eventstore.perfmodel.changepoint.DetectionResult` whose ``index``
        is an offset into ``series``.

    Raises:
        ValueError: If there are fewer than ``reference_points`` + 1 points, or if
            ``reference_points`` is under 2.
    """
    if reference_points < 2:
        raise ValueError(f"reference_points must be >= 2, got {reference_points!r}")
    if len(series) <= reference_points:
        raise ValueError(
            f"need more than {reference_points} points to detect a shift, got {len(series)}"
        )

    values = [value for _, value in series]
    reference = values[:reference_points]
    target = statistics.median(reference)
    # A reference period with no variation at all would divide by zero; one millisecond
    # is below the resolution of the data and keeps the statistic finite.
    sigma = max(statistics.pstdev(reference), 1.0)
    return cusum_detect(values, target=target, sigma=sigma)


def anomaly_scan(
    connection: duckdb.DuckDBPyConnection,
    *,
    service: str,
    start: datetime,
    end: datetime,
    baseline_days: int = DEFAULT_BASELINE_DAYS,
    column: str = "p95_ms",
) -> list[AnomalyScore]:
    """Score every minute in a window against its seasonal baseline.

    The baseline is fitted on ``baseline_days`` of history **with the scored window
    excluded**. Including it would let the anomaly contribute to the centre and
    dispersion it is being compared against, which deflates its own score -- the
    larger the incident, the more it hides itself.

    Args:
        connection: An open warehouse connection.
        service: Exact service name.
        start: Window start, inclusive.
        end: Window end, exclusive.
        baseline_days: How much history to fit on, ending at ``end``.
        column: Rollup column to score.

    Returns:
        One :class:`~eventstore.perfmodel.baseline.AnomalyScore` per minute in the
        window, in time order. Empty if the window holds no buckets.

    Raises:
        ValueError: If there is no history outside the window to fit on.
    """
    history = minute_series(
        connection,
        service=service,
        route=None,
        start=end - timedelta(days=baseline_days),
        end=end,
        column=column,
    )
    baseline = SeasonalBaseline.fit(history, exclude=(start, end))
    window = [(moment, value) for moment, value in history if start <= moment < end]
    return [baseline.score(moment, value) for moment, value in window]
