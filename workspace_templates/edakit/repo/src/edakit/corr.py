"""Correlation and simple descriptive statistics."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class Summary:
    """Descriptive statistics for one numeric column."""

    count: int
    mean: float
    median: float
    stdev: float
    minimum: float
    maximum: float
    q1: float
    q3: float

    @property
    def iqr(self) -> float:
        """The interquartile range."""
        return self.q3 - self.q1

    @property
    def skew_direction(self) -> str:
        """A coarse read on asymmetry.

        Deliberately coarse: the point is to flag that a column is not symmetric, so
        the reader knows the mean is a poor summary, rather than to quantify it.
        """
        if self.mean > self.median:
            return "right"
        if self.mean < self.median:
            return "left"
        return "none"


def summarise(values: list[float]) -> Summary:
    """Compute descriptive statistics for a numeric series.

    Args:
        values: The series.

    Returns:
        A :class:`Summary`.

    Raises:
        ValueError: If the series is empty.
    """
    if not values:
        raise ValueError("cannot summarise an empty series")

    from edakit.outliers import quantile

    ordered = sorted(values)
    return Summary(
        count=len(values),
        mean=statistics.fmean(values),
        median=statistics.median(values),
        stdev=statistics.pstdev(values) if len(values) > 1 else 0.0,
        minimum=ordered[0],
        maximum=ordered[-1],
        q1=quantile(ordered, 0.25),
        q3=quantile(ordered, 0.75),
    )


def pearson(xs: list[float], ys: list[float]) -> float:
    """Return the Pearson correlation coefficient.

    Args:
        xs: First series.
        ys: Second series, the same length as ``xs``.

    Returns:
        The coefficient in [-1, 1]. Returns 0.0 when either series is constant,
        because correlation is undefined there and 0.0 is the reading that will not
        mislead a heatmap.

    Raises:
        ValueError: If the series differ in length or have fewer than two points.
    """
    if len(xs) != len(ys):
        raise ValueError(f"series must be the same length, got {len(xs)} and {len(ys)}")
    if len(xs) < 2:
        raise ValueError("correlation needs at least two points")

    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    dx = [x - mean_x for x in xs]
    dy = [y - mean_y for y in ys]

    numerator = sum(a * b for a, b in zip(dx, dy, strict=True))
    denominator = math.sqrt(sum(a * a for a in dx)) * math.sqrt(sum(b * b for b in dy))
    if denominator == 0:
        return 0.0
    # Clamped: accumulated float error can nudge a perfect correlation past 1.0.
    return max(-1.0, min(1.0, numerator / denominator))


def spearman(xs: list[float], ys: list[float]) -> float:
    """Return the Spearman rank correlation.

    Pearson on the ranks, so it measures monotonic rather than linear association and
    is not thrown off by a single extreme value.

    Args:
        xs: First series.
        ys: Second series, the same length as ``xs``.

    Returns:
        The coefficient in [-1, 1].
    """
    return pearson(_ranks(xs), _ranks(ys))


def _ranks(values: list[float]) -> list[float]:
    """Return average ranks, so tied values share a rank rather than an arbitrary order."""
    ordered = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(ordered):
        end = position
        while end + 1 < len(ordered) and values[ordered[end + 1]] == values[ordered[position]]:
            end += 1
        average = (position + end) / 2 + 1
        for index in range(position, end + 1):
            ranks[ordered[index]] = average
        position = end + 1
    return ranks


def correlation_matrix(
    columns: dict[str, list[float]], method: str = "pearson"
) -> dict[str, dict[str, float]]:
    """Compute a correlation matrix over numeric columns.

    Args:
        columns: Mapping of column name to series. All series must be the same length.
        method: ``"pearson"`` or ``"spearman"``.

    Returns:
        A nested mapping, keys in sorted order so the output is stable.

    Raises:
        ValueError: If the method is unknown.
    """
    if method not in {"pearson", "spearman"}:
        raise ValueError(f"unknown method {method!r}")
    correlate = pearson if method == "pearson" else spearman

    names = sorted(columns)
    matrix: dict[str, dict[str, float]] = {}
    for left in names:
        matrix[left] = {}
        for right in names:
            matrix[left][right] = 1.0 if left == right else correlate(columns[left], columns[right])
    return matrix


def highly_correlated_pairs(
    matrix: dict[str, dict[str, float]], threshold: float = 0.9
) -> list[tuple[str, str, float]]:
    """Return column pairs whose absolute correlation meets a threshold.

    Used to flag redundant features. Each pair appears once, in sorted order.

    Args:
        matrix: A correlation matrix.
        threshold: Absolute correlation to flag at.

    Returns:
        ``(left, right, coefficient)`` tuples, sorted by descending absolute value.
    """
    seen: set[frozenset[str]] = set()
    pairs: list[tuple[str, str, float]] = []
    for left, row in matrix.items():
        for right, value in row.items():
            if left == right:
                continue
            key = frozenset({left, right})
            if key in seen or abs(value) < threshold:
                continue
            seen.add(key)
            pairs.append((min(left, right), max(left, right), value))
    return sorted(pairs, key=lambda item: (-abs(item[2]), item[0], item[1]))
