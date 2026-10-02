"""A seasonality-adjusted baseline, and anomaly scores against it.

**Traffic is seasonal and a flat baseline is a lie.** Tuesday 14:00 and Sunday 03:00 do
not have the same latency, the same throughput or the same error rate, and a single
mean over a fortnight sits between them -- high enough to hide a real Sunday regression,
low enough to page somebody every Tuesday. The baseline here is therefore keyed by
**hour of week**: 168 buckets, each holding the history of one recurring hour.

**The centre is a median and the dispersion is a MAD, not a mean and a standard
deviation.** One ten-minute incident inside a bucket's history moves the mean a little
and the standard deviation a lot -- and a standard deviation inflated by last week's
incident is exactly what stops this week's incident from scoring above threshold. The
median and the median absolute deviation both have a breakdown point of 50%: half the
history would have to be anomalous before they move.

**A baseline must not include the window it is scoring.** Fitting on a range that
contains the anomaly pulls the centre towards it and inflates the dispersion, which
deflates the score of the very point under test. :meth:`SeasonalBaseline.fit` takes an
explicit ``exclude`` range for this reason, and the API passes the window it is about to
score.

Buckets with too little history fall back to the pooled estimate rather than reporting a
confident score from three observations; :attr:`AnomalyScore.sample_size` lets the caller
see which happened.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence

#: Hours in a week; the number of seasonal buckets.
HOURS_PER_WEEK = 168
#: A bucket with fewer observations than this falls back to the pooled estimate.
MIN_BUCKET_OBSERVATIONS = 4
#: Scales the MAD so that, for normally distributed data, it estimates the standard
#: deviation. 0.6745 is the normal distribution's 75th percentile.
MAD_TO_SIGMA = 1.4826
#: Floor on dispersion, in the metric's own units. Without it a bucket whose history is
#: perfectly constant has a MAD of zero and every later observation scores infinity.
MIN_DISPERSION = 1e-9


def hour_of_week(moment: datetime) -> int:
    """Return the seasonal bucket for a timestamp, in ``[0, 168)``.

    Monday 00:00 UTC is bucket 0, matching :meth:`datetime.weekday`.

    Args:
        moment: A timezone-aware UTC timestamp.

    Returns:
        The bucket index.
    """
    return moment.weekday() * 24 + moment.hour


@dataclass(frozen=True)
class AnomalyScore:
    """How unusual one observation is against its seasonal bucket.

    Attributes:
        value: The observation.
        expected: The bucket's median.
        dispersion: The bucket's scaled MAD.
        z_score: ``(value - expected) / dispersion``. Robust, so it is not directly
            comparable to a classical z-score, but the familiar thresholds (3, 4) are
            close enough to be useful.
        bucket: Hour-of-week index the observation was scored against.
        sample_size: Observations in that bucket's history. Below
            :data:`MIN_BUCKET_OBSERVATIONS` the pooled estimate was used instead.
        seasonal: Whether a real bucket estimate was used rather than the pooled one.
    """

    value: float
    expected: float
    dispersion: float
    z_score: float
    bucket: int
    sample_size: int
    seasonal: bool

    def as_dict(self) -> dict[str, float | int | bool]:
        """Return the score as a JSON-serialisable dict."""
        return {
            "value": self.value,
            "expected": self.expected,
            "dispersion": self.dispersion,
            "z_score": self.z_score,
            "bucket": self.bucket,
            "sample_size": self.sample_size,
            "seasonal": self.seasonal,
        }


def scaled_mad(values: Sequence[float]) -> float:
    """Return the median absolute deviation, scaled to be comparable to a sigma.

    Args:
        values: At least one observation.

    Returns:
        ``1.4826 * median(|x - median(x)|)``, floored at :data:`MIN_DISPERSION`.

    Raises:
        ValueError: If ``values`` is empty.
    """
    if not values:
        raise ValueError("MAD of an empty sample is undefined")
    centre = statistics.median(values)
    deviation = statistics.median([abs(value - centre) for value in values])
    return max(MAD_TO_SIGMA * deviation, MIN_DISPERSION)


@dataclass(frozen=True)
class SeasonalBaseline:
    """Per-hour-of-week centres and dispersions, with a pooled fallback.

    Attributes:
        centres: Bucket index -> median.
        dispersions: Bucket index -> scaled MAD.
        counts: Bucket index -> number of observations fitted.
        pooled_centre: Median over every observation.
        pooled_dispersion: Scaled MAD over every observation.
    """

    centres: dict[int, float]
    dispersions: dict[int, float]
    counts: dict[int, int]
    pooled_centre: float
    pooled_dispersion: float

    @classmethod
    def fit(
        cls,
        observations: Iterable[tuple[datetime, float]],
        *,
        exclude: tuple[datetime, datetime] | None = None,
    ) -> SeasonalBaseline:
        """Fit a baseline from historical observations.

        Args:
            observations: ``(timestamp, value)`` pairs. Timestamps must be
                timezone-aware UTC.
            exclude: A half-open ``[start, end)`` range to leave out of the fit.
                **Pass the window you are about to score.** A baseline fitted on a
                range containing the anomaly is pulled towards it and inflated by it,
                and will under-score it.

        Returns:
            A fitted :class:`SeasonalBaseline`.

        Raises:
            ValueError: If no observations survive the exclusion. Scoring against a
                baseline with no history is meaningless and the caller must be told,
                not handed zeros.
        """
        buckets: dict[int, list[float]] = {}
        pooled: list[float] = []
        for moment, value in observations:
            if exclude is not None and exclude[0] <= moment < exclude[1]:
                continue
            buckets.setdefault(hour_of_week(moment), []).append(value)
            pooled.append(value)

        if not pooled:
            raise ValueError("no observations left to fit a baseline from")

        return cls(
            centres={index: statistics.median(vs) for index, vs in buckets.items()},
            dispersions={index: scaled_mad(vs) for index, vs in buckets.items()},
            counts={index: len(vs) for index, vs in buckets.items()},
            pooled_centre=statistics.median(pooled),
            pooled_dispersion=scaled_mad(pooled),
        )

    def score(self, moment: datetime, value: float) -> AnomalyScore:
        """Score one observation against its seasonal bucket.

        Args:
            moment: When the observation happened, timezone-aware UTC.
            value: The observed value.

        Returns:
            An :class:`AnomalyScore`. Buckets with fewer than
            :data:`MIN_BUCKET_OBSERVATIONS` observations are scored against the
            pooled estimate and reported with ``seasonal=False``.
        """
        bucket = hour_of_week(moment)
        count = self.counts.get(bucket, 0)
        seasonal = count >= MIN_BUCKET_OBSERVATIONS
        centre = self.centres[bucket] if seasonal else self.pooled_centre
        dispersion = self.dispersions[bucket] if seasonal else self.pooled_dispersion
        return AnomalyScore(
            value=float(value),
            expected=float(centre),
            dispersion=float(dispersion),
            z_score=(value - centre) / dispersion,
            bucket=bucket,
            sample_size=count,
            seasonal=seasonal,
        )
