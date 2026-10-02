"""Detecting that performance changed and staying changed.

Two detectors, because they answer different questions and the difference is the whole
reason this module is not one function.

**EWMA** tracks an exponentially weighted mean and alarms when it leaves a control band.
Its memory is geometric: an observation's influence decays by ``(1 - alpha)`` every step.
That makes it excellent at spotting a *spike* and poor at spotting a small *sustained*
shift, because a shift of half a standard deviation never moves the weighted mean far
enough to leave the band before the band itself widens to its asymptote.

**CUSUM** accumulates signed deviations from target, each one slashed by a slack ``k``,
and alarms when the running sum crosses a decision interval ``h``. It has no memory decay
at all, so a shift that is individually invisible accumulates until it is not. That is
exactly the shape of a performance regression introduced by a deploy: nothing about any
single request looks wrong, and the service is permanently worse.

**The rule of thumb this service follows:** EWMA for alerting on incidents, CUSUM for
deploy verification. Using EWMA for the second job does not fail loudly -- it detects the
regression *eventually*, usually after the deploy window has closed and the comparison
has already been reported as clean.

Both detectors are expressed in units of ``sigma`` so that ``k`` and ``h`` are
dimensionless and can be reused across metrics with wildly different scales.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

#: CUSUM slack, in sigma. The classic choice is half the shift you want to detect, so
#: 0.5 is tuned for a one-sigma sustained shift.
DEFAULT_SLACK_K = 0.5
#: CUSUM decision interval, in sigma. With k = 0.5 this is the textbook pairing, giving
#: an in-control average run length of roughly 465 observations.
DEFAULT_DECISION_H = 5.0
#: EWMA smoothing factor. Smaller means longer memory and a narrower control band.
DEFAULT_ALPHA = 0.3
#: EWMA control limit, in sigma. Three-sigma, as on any Shewhart-style chart.
DEFAULT_CONTROL_L = 3.0


@dataclass(frozen=True)
class DetectionResult:
    """What a detector saw.

    Attributes:
        alarmed: Whether the detector ever crossed its limit.
        index: Index of the first observation at which it crossed, or ``None``.
        statistic: The detector's statistic at every step, for plotting and for
            explaining an alarm to whoever gets paged.
        limit: The limit the statistic was compared against. Constant for CUSUM;
            for EWMA it is the final, asymptotic band since the band widens with time.
    """

    alarmed: bool
    index: int | None
    statistic: list[float] = field(default_factory=list)
    limit: float = 0.0

    @property
    def delay(self) -> int | None:
        """Alias for :attr:`index`, read as "how many observations it took"."""
        return self.index

    def as_dict(self) -> dict[str, object]:
        """Return the result as a JSON-serialisable dict."""
        return {"alarmed": self.alarmed, "index": self.index, "limit": self.limit}


def ewma_detect(
    values: Sequence[float],
    *,
    target: float,
    sigma: float,
    alpha: float = DEFAULT_ALPHA,
    control_l: float = DEFAULT_CONTROL_L,
) -> DetectionResult:
    """Run an EWMA control chart over ``values``.

    The control band is the exact time-varying one,
    ``L * sigma * sqrt(alpha/(2-alpha) * (1 - (1-alpha)**(2(t+1))))``, rather than its
    asymptote. Using the asymptote from the first observation makes the chart
    insensitive early in a series, which is precisely when a deploy is being watched.

    Args:
        values: The series, in observation order.
        target: The in-control mean.
        sigma: The in-control standard deviation, strictly positive.
        alpha: Smoothing factor in ``(0, 1]``.
        control_l: Control limit in sigma.

    Returns:
        A :class:`DetectionResult` whose ``statistic`` is the weighted mean at each
        step.

    Raises:
        ValueError: If ``sigma`` is not positive or ``alpha`` is outside ``(0, 1]``.
    """
    if sigma <= 0:
        raise ValueError(f"sigma must be > 0, got {sigma!r}")
    if not 0.0 < alpha <= 1.0:
        raise ValueError(f"alpha must be in (0, 1], got {alpha!r}")

    smoothed = target
    path: list[float] = []
    first_alarm: int | None = None
    final_limit = 0.0

    for step, value in enumerate(values):
        smoothed = alpha * value + (1.0 - alpha) * smoothed
        path.append(smoothed)
        variance_factor = (alpha / (2.0 - alpha)) * (1.0 - (1.0 - alpha) ** (2 * (step + 1)))
        limit = control_l * sigma * variance_factor**0.5
        final_limit = limit
        if first_alarm is None and abs(smoothed - target) > limit:
            first_alarm = step

    return DetectionResult(
        alarmed=first_alarm is not None,
        index=first_alarm,
        statistic=path,
        limit=final_limit,
    )


def cusum_detect(
    values: Sequence[float],
    *,
    target: float,
    sigma: float,
    slack_k: float = DEFAULT_SLACK_K,
    decision_h: float = DEFAULT_DECISION_H,
) -> DetectionResult:
    """Run a two-sided tabular CUSUM over ``values``.

    Both the upward and downward accumulators are maintained; the reported statistic
    is the larger of the two at each step, because an alarm is an alarm whichever
    direction the shift went.

    Args:
        values: The series, in observation order.
        target: The in-control mean.
        sigma: The in-control standard deviation, strictly positive.
        slack_k: Slack in sigma. Deviations smaller than this are absorbed, which is
            what keeps ordinary noise from accumulating into a false alarm.
        decision_h: Decision interval in sigma.

    Returns:
        A :class:`DetectionResult` whose ``statistic`` is ``max(S_hi, S_lo)`` at each
        step, in sigma units.

    Raises:
        ValueError: If ``sigma`` is not positive, or ``slack_k`` or ``decision_h`` is
            negative.
    """
    if sigma <= 0:
        raise ValueError(f"sigma must be > 0, got {sigma!r}")
    if slack_k < 0 or decision_h <= 0:
        raise ValueError(f"slack_k must be >= 0 and decision_h > 0, got {slack_k!r}, {decision_h!r}")

    high = low = 0.0
    path: list[float] = []
    first_alarm: int | None = None

    for step, value in enumerate(values):
        standardised = (value - target) / sigma
        high = max(0.0, high + standardised - slack_k)
        low = max(0.0, low - standardised - slack_k)
        worst = max(high, low)
        path.append(worst)
        if first_alarm is None and worst > decision_h:
            first_alarm = step

    return DetectionResult(
        alarmed=first_alarm is not None,
        index=first_alarm,
        statistic=path,
        limit=decision_h,
    )
