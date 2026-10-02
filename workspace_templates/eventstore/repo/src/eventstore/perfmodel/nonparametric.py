"""Distribution-free comparison of two latency samples.

**Why not a t-test.** Latency is not normal and is not close. It is bounded below by the
speed of the fastest possible path, unbounded above, and heavily right-skewed by retries,
cold caches and garbage collection. A t-test on such a sample compares means, and a mean
latency is dominated by exactly the tail that a handful of pathological requests produce
-- so a release that made the median 20% worse and the tail slightly better can be
declared an improvement. The Mann-Whitney U test compares *ranks*, which means it asks
the question that actually matters for a deploy decision: if you pick one request from
each release at random, which is more likely to be slower?

**Ties matter here.** Latencies are recorded in whole milliseconds, so ties are common
rather than a theoretical edge case, and the tie correction to the variance is not
optional: without it the variance is overstated, the z-score is pulled towards zero and
a real regression goes unreported. The correction term is the standard one,
``sum(t³ - t) / (N(N-1))`` over tie groups.

The p-value is a normal approximation with a continuity correction, valid once both
samples are reasonably sized. Below :data:`MIN_SAMPLE_FOR_NORMAL_APPROX` observations per
group the approximation is not trustworthy and the result says so rather than returning a
confident-looking number.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

#: Below this many observations per group the normal approximation to U is unreliable.
#: Reported rather than enforced: a caller comparing two tiny canaries still wants the
#: effect size, it just must not quote the p-value.
MIN_SAMPLE_FOR_NORMAL_APPROX = 8


@dataclass(frozen=True)
class ComparisonResult:
    """The outcome of comparing two samples.

    Attributes:
        u_statistic: The U statistic for the first sample.
        z_score: Tie-corrected normal approximation of U, continuity-corrected.
        p_value: Two-sided p-value from ``z_score``.
        effect_size: Rank-biserial correlation in ``[-1, 1]``. Positive means the
            first sample tends to be *slower*. Unlike the p-value this does not grow
            with sample size, so it is the number to act on.
        n_a: Size of the first sample.
        n_b: Size of the second sample.
        approximation_valid: Whether both samples reach
            :data:`MIN_SAMPLE_FOR_NORMAL_APPROX`. When false, ``p_value`` must not be
            quoted.
    """

    u_statistic: float
    z_score: float
    p_value: float
    effect_size: float
    n_a: int
    n_b: int
    approximation_valid: bool

    def as_dict(self) -> dict[str, float | int | bool]:
        """Return the result as a JSON-serialisable dict."""
        return {
            "u_statistic": self.u_statistic,
            "z_score": self.z_score,
            "p_value": self.p_value,
            "effect_size": self.effect_size,
            "n_a": self.n_a,
            "n_b": self.n_b,
            "approximation_valid": self.approximation_valid,
        }


def rank_with_ties(values: Sequence[float]) -> list[float]:
    """Return 1-based ranks of ``values``, averaging the ranks of tied observations.

    Args:
        values: The pooled sample.

    Returns:
        Ranks in the same order as ``values``. Three-way ties at ranks 4, 5 and 6 all
        receive 5.0.
    """
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
            end += 1
        # Ranks are 1-based, so the group spans ranks position+1 .. end+1.
        average = (position + 1 + end + 1) / 2.0
        for index in order[position : end + 1]:
            ranks[index] = average
        position = end + 1
    return ranks


def _tie_correction(values: Sequence[float]) -> float:
    """Return ``sum(t**3 - t)`` over tie groups in the pooled sample."""
    return float(sum(size**3 - size for size in Counter(values).values() if size > 1))


def mann_whitney_u(sample_a: Sequence[float], sample_b: Sequence[float]) -> ComparisonResult:
    """Compare two independent samples with the Mann-Whitney U test.

    Args:
        sample_a: First sample, conventionally the candidate or new release.
        sample_b: Second sample, conventionally the baseline.

    Returns:
        A :class:`ComparisonResult`. ``effect_size`` is positive when ``sample_a``
        tends to hold the larger values.

    Raises:
        ValueError: If either sample is empty.

    Example:
        ``[1, 2, 3]`` against ``[4, 5, 6]``: no value of A exceeds any value of B, so
        ``u_statistic`` is 0.0 and ``effect_size`` is -1.0.
    """
    if not sample_a or not sample_b:
        raise ValueError("both samples must be non-empty")

    n_a, n_b = len(sample_a), len(sample_b)
    pooled = list(sample_a) + list(sample_b)
    ranks = rank_with_ties(pooled)

    rank_sum_a = sum(ranks[:n_a])
    u_a = rank_sum_a - n_a * (n_a + 1) / 2.0

    total = n_a * n_b
    mean_u = total / 2.0
    n = n_a + n_b
    correction = _tie_correction(pooled)
    variance = (total / 12.0) * ((n + 1) - correction / (n * (n - 1.0)))

    if variance <= 0:
        # Every observation in both samples is identical: U is exactly its mean and
        # there is nothing to detect.
        z_score = 0.0
        p_value = 1.0
    else:
        # Continuity correction, towards the mean from whichever side U falls on.
        deviation = abs(u_a - mean_u) - 0.5
        z_score = math.copysign(max(deviation, 0.0), u_a - mean_u) / math.sqrt(variance)
        p_value = 2.0 * (1.0 - _standard_normal_cdf(abs(z_score)))

    return ComparisonResult(
        u_statistic=u_a,
        z_score=z_score,
        p_value=min(1.0, max(0.0, p_value)),
        # Rank-biserial correlation: 2*U/(n_a*n_b) - 1.
        effect_size=(2.0 * u_a / total) - 1.0,
        n_a=n_a,
        n_b=n_b,
        approximation_valid=min(n_a, n_b) >= MIN_SAMPLE_FOR_NORMAL_APPROX,
    )


def _standard_normal_cdf(x: float) -> float:
    """Return the standard normal CDF at ``x``, via :func:`math.erf`."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
