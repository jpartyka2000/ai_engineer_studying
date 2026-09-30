"""Missing-value analysis and imputation.

Imputation is fit on one dataset and applied to another, so the learned values are
kept in an explicit object rather than recomputed at transform time. Recomputing is
how train/serve skew gets introduced.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum

from edakit.schema_infer import ColumnType, is_null


class Strategy(StrEnum):
    """How to fill a column's missing values."""

    MEAN = "mean"
    MEDIAN = "median"
    MODE = "mode"
    CONSTANT = "constant"
    DROP_ROW = "drop_row"


@dataclass
class MissingReport:
    """Where the holes are in a table."""

    total_rows: int
    null_counts: dict[str, int] = field(default_factory=dict)
    complete_rows: int = 0

    @property
    def null_fractions(self) -> dict[str, float]:
        """Null proportion per column."""
        if self.total_rows == 0:
            return dict.fromkeys(self.null_counts, 0.0)
        return {name: count / self.total_rows for name, count in self.null_counts.items()}

    @property
    def completeness(self) -> float:
        """Fraction of rows with no missing values at all."""
        if self.total_rows == 0:
            return 1.0
        return self.complete_rows / self.total_rows

    def columns_above(self, threshold: float) -> list[str]:
        """Return columns whose null fraction meets or exceeds a threshold.

        Args:
            threshold: A fraction between 0 and 1.

        Returns:
            Column names, sorted, so the result is stable for reporting.
        """
        return sorted(
            name for name, fraction in self.null_fractions.items() if fraction >= threshold
        )


def analyse_missing(rows: list[dict[str, str | None]]) -> MissingReport:
    """Count missing values per column and overall row completeness.

    Args:
        rows: The table.

    Returns:
        A :class:`MissingReport`.
    """
    if not rows:
        return MissingReport(total_rows=0)

    names = list(rows[0].keys())
    counts = dict.fromkeys(names, 0)
    complete = 0
    for row in rows:
        row_complete = True
        for name in names:
            if is_null(row.get(name)):
                counts[name] += 1
                row_complete = False
        complete += row_complete
    return MissingReport(total_rows=len(rows), null_counts=counts, complete_rows=complete)


@dataclass
class Imputer:
    """A fitted imputer.

    Holds the values learned at fit time so transform is a pure lookup. Recomputing
    statistics during transform would make the output depend on whichever batch it
    was applied to, which is the classic source of train/serve skew.
    """

    strategies: dict[str, Strategy]
    fill_values: dict[str, str] = field(default_factory=dict)
    constants: dict[str, str] = field(default_factory=dict)

    @property
    def is_fitted(self) -> bool:
        """Whether :func:`fit_imputer` has produced fill values."""
        return bool(self.fill_values) or Strategy.DROP_ROW in self.strategies.values()

    def transform(self, rows: list[dict[str, str | None]]) -> list[dict[str, str | None]]:
        """Apply the learned fills to a table.

        Args:
            rows: The table to fill.

        Returns:
            A new list of new dicts. The input is never mutated, so a caller can
            compare before and after.
        """
        drop_columns = [
            name for name, strategy in self.strategies.items() if strategy == Strategy.DROP_ROW
        ]

        filled: list[dict[str, str | None]] = []
        for row in rows:
            if any(is_null(row.get(name)) for name in drop_columns):
                continue
            new_row = dict(row)
            for name, value in self.fill_values.items():
                if is_null(new_row.get(name)):
                    new_row[name] = value
            filled.append(new_row)
        return filled


def fit_imputer(
    rows: list[dict[str, str | None]],
    strategies: dict[str, Strategy],
    constants: dict[str, str] | None = None,
    column_types: dict[str, ColumnType] | None = None,
) -> Imputer:
    """Learn fill values from a table.

    Args:
        rows: The table to learn from.
        strategies: Column name to :class:`Strategy`.
        constants: Fill values for columns using ``CONSTANT``.
        column_types: Inferred types, used to reject numeric strategies on
            non-numeric columns rather than failing obscurely later.

    Returns:
        A fitted :class:`Imputer`.

    Raises:
        ValueError: If a ``CONSTANT`` column has no constant supplied, or a numeric
            strategy is requested for a column that is not numeric.
    """
    constants = constants or {}
    types = column_types or {}
    fills: dict[str, str] = {}

    for name, strategy in strategies.items():
        if strategy == Strategy.DROP_ROW:
            continue
        if strategy == Strategy.CONSTANT:
            if name not in constants:
                raise ValueError(f"column {name!r} uses CONSTANT but no constant was given")
            fills[name] = constants[name]
            continue

        present = [str(row.get(name)).strip() for row in rows if not is_null(row.get(name))]
        if not present:
            # Nothing to learn from. Skipping leaves the column untouched, which is
            # more honest than inventing a value.
            continue

        if strategy == Strategy.MODE:
            # most_common is insertion-ordered on ties, so sort first to make the
            # choice deterministic across runs.
            fills[name] = Counter(sorted(present)).most_common(1)[0][0]
            continue

        declared = types.get(name)
        if declared is not None and declared not in {ColumnType.INTEGER, ColumnType.FLOAT}:
            raise ValueError(
                f"column {name!r} is {declared} but strategy {strategy} is numeric-only"
            )
        try:
            numbers = [float(value) for value in present]
        except ValueError as exc:
            raise ValueError(
                f"column {name!r} is not numeric, so strategy {strategy} cannot be used"
            ) from exc

        centre = statistics.fmean(numbers) if strategy == Strategy.MEAN else statistics.median(numbers)
        # Integers stay integers, so a filled column does not silently become floats.
        if declared == ColumnType.INTEGER and centre == int(centre):
            fills[name] = str(int(centre))
        else:
            fills[name] = repr(round(centre, 10))

    return Imputer(strategies=dict(strategies), fill_values=fills, constants=constants)
