"""Revenue analytics.

Pure functions over plain numbers: no ORM, no numpy, no scipy. That keeps them
unit-testable against hand-computed constants, which is what makes the statistics
verifiable rather than merely plausible.
"""

import math
from dataclasses import dataclass

#: z for a two-sided 95% interval. Hardcoded rather than pulled from a stats
#: library, because adding scipy for one constant is not worth it.
Z_95 = 1.959963984540054


@dataclass(frozen=True)
class Interval:
    """A confidence interval."""

    lower: float
    upper: float

    @property
    def width(self) -> float:
        """The interval's width."""
        return self.upper - self.lower


def wilson_interval(successes: int, trials: int, z: float = Z_95) -> Interval:
    """Return a Wilson score interval for a binomial proportion.

    Preferred over the normal approximation because it stays inside [0, 1] and
    behaves sensibly at small samples and at proportions near 0 or 1 -- exactly the
    cases a plan-conversion rate runs into.

    Args:
        successes: Number of successes.
        trials: Number of trials. Zero yields ``Interval(0.0, 0.0)`` rather than
            raising, so a brand-new cohort does not break a dashboard.
        z: z-score for the desired confidence level.

    Returns:
        The :class:`Interval`.

    Raises:
        ValueError: If ``successes`` is negative or exceeds ``trials``.
    """
    if trials == 0:
        return Interval(0.0, 0.0)
    if successes < 0 or successes > trials:
        raise ValueError(f"successes must be within 0..{trials}, got {successes}")

    proportion = successes / trials
    denominator = 1 + z**2 / trials
    centre = proportion + z**2 / (2 * trials)
    spread = z * math.sqrt(proportion * (1 - proportion) / trials + z**2 / (4 * trials**2))

    # Rounded before clamping. At p=1 the algebra cancels to exactly 1.0, but in
    # floating point it lands on 0.9999999999999999, which min() will not clamp --
    # so an "all successes" cohort would report an upper bound just under certainty.
    # Twelve places is far more precision than a proportion needs and makes the
    # boundary exact.
    lower = round((centre - spread) / denominator, 12)
    upper = round((centre + spread) / denominator, 12)
    return Interval(lower=max(0.0, lower), upper=min(1.0, upper))


def month_over_month_growth(monthly_totals: list[int]) -> list[float]:
    """Return period-over-period growth rates for a series of totals.

    Args:
        monthly_totals: Totals in chronological order.

    Returns:
        One growth rate per transition, so the result is one element shorter than the
        input. A month following a zero yields 0.0 rather than infinity, because a
        dashboard cannot render infinity and the true rate is undefined.
    """
    growth: list[float] = []
    for previous, current in zip(monthly_totals, monthly_totals[1:], strict=False):
        if previous == 0:
            growth.append(0.0)
        else:
            growth.append((current - previous) / previous)
    return growth


def ewma(values: list[float], alpha: float) -> list[float]:
    """Return the exponentially weighted moving average of a series.

    Used to smooth daily revenue before change detection, so a single spike does not
    read as a trend.

    Args:
        values: The series, in order.
        alpha: Smoothing factor in (0, 1]. Higher reacts faster.

    Returns:
        The smoothed series, the same length as the input. Seeded with the first
        value rather than with zero, which would otherwise drag the whole series
        down at the start.

    Raises:
        ValueError: If ``alpha`` is outside (0, 1].
    """
    if not 0 < alpha <= 1:
        raise ValueError(f"alpha must be in (0, 1], got {alpha}")
    if not values:
        return []

    smoothed = [float(values[0])]
    for value in values[1:]:
        smoothed.append(alpha * value + (1 - alpha) * smoothed[-1])
    return smoothed


def detect_change_points(values: list[float], alpha: float, threshold: float) -> list[int]:
    """Return indices where a series departs sharply from its smoothed trend.

    Args:
        values: The series, in order.
        alpha: Smoothing factor for the underlying EWMA.
        threshold: Relative deviation from the smoothed value that counts as a
            change, e.g. ``0.5`` for 50%.

    Returns:
        Indices of the flagged points. Index 0 is never flagged, because the EWMA is
        seeded from it and so has nothing to deviate from.
    """
    smoothed = ewma(values, alpha)
    flagged: list[int] = []
    for index in range(1, len(values)):
        baseline = smoothed[index - 1]
        if baseline == 0:
            continue
        if abs(values[index] - baseline) / abs(baseline) >= threshold:
            flagged.append(index)
    return flagged
