"""Confidence intervals: Wilson for proportions, bootstrap for everything else.

Two intervals, chosen for two different situations.

**Wilson, for error rates.** An error rate is a binomial proportion, and the quantity
we care about most -- "is this endpoint broken?" -- lives near zero, where the normal
approximation ``p ± z·sqrt(p(1-p)/n)`` produces negative lower bounds and, at zero
errors, an interval of exactly zero width. Reporting "0% ± 0%" after five requests is
the specific failure this module exists to avoid. Wilson has no such degenerate case:
0 of 5 gives an upper bound near 0.43, which correctly reads as "we have no idea yet".

**Bootstrap, for statistics with no closed form.** Latency medians and the shift between
two latency distributions have no tidy sampling distribution, so the interval is obtained
by resampling. The resampling is **seeded by the caller** and the seed is part of the
result: a confidence interval that is different every time it is computed cannot be put
in a report, compared against yesterday's, or asserted in a test.

Pure stdlib. ``Z_95`` is a constant, not a lookup into a distribution table, because the
only quantile this service ever needs is the 95% two-sided one.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Sequence

#: Two-sided 95% normal quantile. The only one used here; if a second confidence level
#: is ever needed, add a named constant rather than a distribution dependency.
Z_95 = 1.959963984540054


@dataclass(frozen=True)
class Interval:
    """A closed interval ``[low, high]``.

    Attributes:
        low: Lower bound.
        high: Upper bound.
    """

    low: float
    high: float

    @property
    def width(self) -> float:
        """Interval width. Narrower means more evidence."""
        return self.high - self.low

    def contains(self, value: float) -> bool:
        """Return whether ``value`` lies inside the closed interval."""
        return self.low <= value <= self.high

    def as_dict(self) -> dict[str, float]:
        """Return the interval as a JSON-serialisable dict."""
        return {"low": self.low, "high": self.high}


def wilson_interval(successes: int, trials: int, z: float = Z_95) -> Interval:
    """Return the Wilson score interval for a binomial proportion.

    Args:
        successes: Number of successes, ``0 <= successes <= trials``.
        trials: Number of trials.
        z: Normal quantile for the desired confidence level.

    Returns:
        An :class:`Interval` inside ``[0, 1]``. Zero trials returns ``[0, 1]`` --
        total ignorance, which is the honest answer before any observation and is
        distinguishable from a measured zero.

    Raises:
        ValueError: If the counts are impossible.

    Example:
        0 errors in 5 requests gives roughly ``[0.0, 0.4344]``, not ``[0.0, 0.0]``.
    """
    if trials < 0 or successes < 0:
        raise ValueError(f"counts must be non-negative, got {successes}/{trials}")
    if successes > trials:
        raise ValueError(f"successes ({successes}) cannot exceed trials ({trials})")
    if trials == 0:
        return Interval(0.0, 1.0)

    n = float(trials)
    p = successes / n
    denominator = 1.0 + (z * z) / n
    centre = (p + (z * z) / (2.0 * n)) / denominator
    spread = (z * math.sqrt(p * (1.0 - p) / n + (z * z) / (4.0 * n * n))) / denominator
    # Round before clamping. At successes == trials the algebra cancels to exactly 1.0
    # but floating point lands a few ulps below, and min(1.0, x) cannot clamp a value
    # that is already under the bound.
    low = max(0.0, round(centre - spread, 12))
    high = min(1.0, round(centre + spread, 12))
    return Interval(low, high)


def bootstrap_ci(
    values: Sequence[float],
    statistic: Callable[[Sequence[float]], float],
    *,
    seed: int,
    resamples: int = 2000,
    confidence: float = 0.95,
) -> Interval:
    """Return a percentile-bootstrap confidence interval for ``statistic``.

    The sample is resampled with replacement ``resamples`` times; the interval is the
    empirical quantile range of the statistic across those resamples.

    Args:
        values: The observed sample.
        statistic: A function from a sample to a single number, e.g.
            ``statistics.median``.
        seed: Seed for the resampling RNG. **Required, keyword-only, and part of the
            contract**: the same arguments must always give the same interval, or two
            runs of the same report disagree and neither can be trusted.
        resamples: Number of bootstrap resamples.
        confidence: Two-sided confidence level in ``(0, 1)``.

    Returns:
        An :class:`Interval`. A one-element sample returns a zero-width interval at
        that value, because every resample is identical.

    Raises:
        ValueError: If the sample is empty, ``resamples`` is not positive, or
            ``confidence`` is outside ``(0, 1)``.
    """
    if not values:
        raise ValueError("cannot bootstrap an empty sample")
    if resamples <= 0:
        raise ValueError(f"resamples must be > 0, got {resamples!r}")
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {confidence!r}")

    rng = random.Random(seed)
    size = len(values)
    estimates = sorted(
        statistic([values[rng.randrange(size)] for _ in range(size)]) for _ in range(resamples)
    )

    tail = (1.0 - confidence) / 2.0
    low_rank = max(1, math.ceil(tail * resamples))
    high_rank = max(1, math.ceil((1.0 - tail) * resamples))
    return Interval(
        low=float(estimates[low_rank - 1]),
        high=float(estimates[min(high_rank, resamples) - 1]),
    )
