"""Latency percentiles.

**Nearest-rank, not interpolated.** Every percentile in this package is an observation
that actually happened. Interpolating between two samples invents a latency no request
ever experienced, and when a service-level objective is written as "p99 under 400ms" the
number it is compared against should be a real measurement. The cost of the choice is
that the percentile moves in steps for small samples, which is honest: with 20 samples
there is no meaningful p99 to report and the step size says so.

The definition used here is the one in NIST's handbook: for ``n`` sorted observations the
``q``-th percentile is the observation at 1-based rank ``ceil(q/100 * n)``, clamped into
``[1, n]``. ``p50`` of an even-length sample is therefore the lower of the two middle
values rather than their mean -- again, a real observation.

No numpy. These functions run on small lists in request handlers and in tests that assert
hand-computed constants; a dependency that would have to be pinned, built and audited
buys nothing here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class LatencySummary:
    """The numbers a latency panel shows, computed once from one sorted pass.

    Attributes:
        count: Number of observations the summary was computed from.
        p50: Median latency in milliseconds, nearest-rank.
        p95: 95th percentile in milliseconds, nearest-rank.
        p99: 99th percentile in milliseconds, nearest-rank.
        max: The slowest observation, which is p100 by definition.
        mean: Arithmetic mean, reported alongside the percentiles rather than
            instead of them -- a mean and a p99 that disagree is the signal.
    """

    count: int
    p50: float
    p95: float
    p99: float
    max: float
    mean: float

    def as_dict(self) -> dict[str, float | int]:
        """Return the summary as a JSON-serialisable dict."""
        return {
            "count": self.count,
            "p50": self.p50,
            "p95": self.p95,
            "p99": self.p99,
            "max": self.max,
            "mean": self.mean,
        }


def percentile(values: Sequence[float], q: float) -> float:
    """Return the nearest-rank ``q``-th percentile of ``values``.

    Args:
        values: Observations. Need not be sorted; this function sorts a copy.
        q: The percentile to compute, in ``[0, 100]``.

    Returns:
        The observation at 1-based rank ``ceil(q/100 * n)``. ``q=0`` returns the
        minimum.

    Raises:
        ValueError: If ``values`` is empty or ``q`` is outside ``[0, 100]``.

    Example:
        For ``values = [1, 2, ..., 100]`` and ``q = 95`` the rank is
        ``ceil(0.95 * 100) = 95``, so the result is ``95``.
    """
    if not 0 <= q <= 100:
        raise ValueError(f"q must be in [0, 100], got {q!r}")
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile of an empty sample is undefined")
    rank = math.ceil((q / 100.0) * len(ordered))
    index = min(max(rank, 1), len(ordered)) - 1
    return float(ordered[index])


def summarize(values: Iterable[float]) -> LatencySummary:
    """Summarise a latency sample.

    Sorts once and indexes three times rather than calling :func:`percentile` three
    times, because the hot caller is a dashboard endpoint summarising a window that
    can hold tens of thousands of observations.

    Args:
        values: Latency observations in milliseconds.

    Returns:
        A :class:`LatencySummary`.

    Raises:
        ValueError: If the sample is empty. An empty window is a real condition and
            the caller has to decide what to render for it; returning zeros here
            would make "no traffic" indistinguishable from "instantaneous".
    """
    ordered = sorted(values)
    count = len(ordered)
    if count == 0:
        raise ValueError("cannot summarise an empty latency sample")

    def at(q: float) -> float:
        rank = math.ceil((q / 100.0) * count)
        return float(ordered[min(max(rank, 1), count) - 1])

    return LatencySummary(
        count=count,
        p50=at(50),
        p95=at(95),
        p99=at(99),
        max=float(ordered[-1]),
        mean=sum(ordered) / count,
    )
