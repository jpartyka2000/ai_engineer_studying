"""Feature scaling.

Every scaler here is fit once and then applied unchanged. ``transform`` never looks at
the data it is transforming -- if it did, applying a scaler to a single row would
produce different numbers than applying it to a batch, which is train/serve skew.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from enum import StrEnum


class ScalerKind(StrEnum):
    """Available scalers."""

    STANDARD = "standard"
    MINMAX = "minmax"
    ROBUST = "robust"


@dataclass(frozen=True)
class Scaler:
    """A fitted scaler.

    Attributes:
        kind: Which scaler this is.
        centre: Value subtracted before dividing (mean, minimum, or median).
        spread: Value divided by (standard deviation, range, or IQR). Never zero:
            :func:`fit_scaler` substitutes 1.0 for a constant column so transform
            cannot divide by zero.
    """

    kind: ScalerKind
    centre: float
    spread: float

    def transform(self, values: list[float]) -> list[float]:
        """Scale a series using the fitted parameters."""
        return [(value - self.centre) / self.spread for value in values]

    def inverse_transform(self, values: list[float]) -> list[float]:
        """Map scaled values back to the original units.

        Needed whenever a prediction has to be reported in the units a human
        understands.
        """
        return [value * self.spread + self.centre for value in values]


def fit_scaler(values: list[float], kind: ScalerKind) -> Scaler:
    """Learn scaling parameters from a series.

    Args:
        values: The series to fit on.
        kind: Which scaler to fit.

    Returns:
        A fitted :class:`Scaler`. A constant column yields ``spread=1.0`` so that
        transforming it produces zeros rather than raising -- a constant feature is
        useless but should not crash a pipeline.

    Raises:
        ValueError: If the series is empty.
    """
    if not values:
        raise ValueError("cannot fit a scaler on an empty series")

    if kind == ScalerKind.STANDARD:
        centre = statistics.fmean(values)
        spread = statistics.pstdev(values)
    elif kind == ScalerKind.MINMAX:
        centre = min(values)
        spread = max(values) - centre
    else:  # ROBUST -- median and IQR, so a few extreme values do not dominate.
        from edakit.outliers import quantile

        ordered = sorted(values)
        centre = statistics.median(values)
        spread = quantile(ordered, 0.75) - quantile(ordered, 0.25)

    return Scaler(kind=kind, centre=centre, spread=spread if spread != 0 else 1.0)
