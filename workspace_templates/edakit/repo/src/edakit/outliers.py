"""Outlier detection.

Two methods, because they disagree in ways that matter: the z-score method assumes
roughly normal data and is dragged around by the very outliers it is looking for,
while the IQR method is robust but flags more on skewed distributions. Callers should
pick deliberately, so neither is the default.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from enum import StrEnum


class Method(StrEnum):
    """How to decide what counts as an outlier."""

    ZSCORE = "zscore"
    IQR = "iqr"
    MODIFIED_ZSCORE = "modified_zscore"


#: Conventional thresholds. Named rather than inlined so a caller overriding them is
#: making a visible choice.
DEFAULT_ZSCORE_THRESHOLD = 3.0
DEFAULT_IQR_MULTIPLIER = 1.5
DEFAULT_MODIFIED_ZSCORE_THRESHOLD = 3.5

#: Scales the median absolute deviation so it estimates the standard deviation of a
#: normal distribution. 1/0.6745, the usual constant.
MAD_SCALE = 0.6745


@dataclass(frozen=True)
class OutlierReport:
    """Which values were flagged, and the bounds that flagged them."""

    method: Method
    indices: tuple[int, ...]
    lower_bound: float | None
    upper_bound: float | None
    total: int

    @property
    def count(self) -> int:
        """How many values were flagged."""
        return len(self.indices)

    @property
    def fraction(self) -> float:
        """Proportion of values flagged, 0.0 for an empty series."""
        if self.total == 0:
            return 0.0
        return self.count / self.total


def quantile(sorted_values: list[float], q: float) -> float:
    """Return a quantile by linear interpolation.

    Implemented here rather than taken from ``statistics.quantiles`` so the
    interpolation method is explicit and matches what the tests assert. Different
    libraries pick different conventions, and silently changing convention shifts
    every bound.

    Args:
        sorted_values: Values in ascending order.
        q: Quantile in [0, 1].

    Returns:
        The interpolated quantile.

    Raises:
        ValueError: If the series is empty or ``q`` is out of range.
    """
    if not sorted_values:
        raise ValueError("cannot take a quantile of an empty series")
    if not 0.0 <= q <= 1.0:
        raise ValueError(f"q must be in [0, 1], got {q}")
    if len(sorted_values) == 1:
        return sorted_values[0]

    position = q * (len(sorted_values) - 1)
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    weight = position - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


def detect_outliers(
    values: list[float],
    method: Method,
    threshold: float | None = None,
) -> OutlierReport:
    """Flag outliers in a numeric series.

    Args:
        values: The series.
        method: Which method to use.
        threshold: Method-specific sensitivity. Defaults to the conventional value.

    Returns:
        An :class:`OutlierReport`. A series of fewer than three values is never
        flagged: with that little data any notion of "unusual" is noise.

    Raises:
        ValueError: If the method is unknown.
    """
    total = len(values)
    if total < 3:
        return OutlierReport(method=method, indices=(), lower_bound=None, upper_bound=None, total=total)

    if method == Method.IQR:
        multiplier = DEFAULT_IQR_MULTIPLIER if threshold is None else threshold
        ordered = sorted(values)
        q1 = quantile(ordered, 0.25)
        q3 = quantile(ordered, 0.75)
        spread = q3 - q1
        lower = q1 - multiplier * spread
        upper = q3 + multiplier * spread

    elif method == Method.ZSCORE:
        limit = DEFAULT_ZSCORE_THRESHOLD if threshold is None else threshold
        mean = statistics.fmean(values)
        deviation = statistics.pstdev(values)
        if deviation == 0:
            # Every value identical: nothing can be unusual.
            return OutlierReport(method, (), None, None, total)
        lower = mean - limit * deviation
        upper = mean + limit * deviation

    elif method == Method.MODIFIED_ZSCORE:
        limit = DEFAULT_MODIFIED_ZSCORE_THRESHOLD if threshold is None else threshold
        median = statistics.median(values)
        mad = statistics.median([abs(v - median) for v in values])
        if mad == 0:
            return OutlierReport(method, (), None, None, total)
        half_width = limit * mad / MAD_SCALE
        lower = median - half_width
        upper = median + half_width

    else:  # pragma: no cover - the enum is exhaustive above
        raise ValueError(f"unknown method {method!r}")

    flagged = tuple(
        index for index, value in enumerate(values) if value < lower or value > upper
    )
    return OutlierReport(method=method, indices=flagged, lower_bound=lower, upper_bound=upper, total=total)


def winsorize(values: list[float], report: OutlierReport) -> list[float]:
    """Clamp flagged values to the report's bounds.

    Preferred over dropping rows when the rest of the row is still useful.

    Args:
        values: The original series.
        report: A report produced from the same series.

    Returns:
        A new list with flagged values clamped. Returned unchanged when the report
        has no bounds.
    """
    if report.lower_bound is None or report.upper_bound is None:
        return list(values)
    return [min(max(value, report.lower_bound), report.upper_bound) for value in values]
