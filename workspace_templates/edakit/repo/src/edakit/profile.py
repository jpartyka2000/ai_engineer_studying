"""Loading tables and producing a whole-dataset profile."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from edakit.corr import Summary, correlation_matrix, highly_correlated_pairs, summarise
from edakit.missing import MissingReport, analyse_missing
from edakit.schema_infer import ColumnProfile, ColumnType, infer_schema, is_null

Row = dict[str, str | None]

#: Columns of these types can be summarised numerically.
NUMERIC_TYPES = frozenset({ColumnType.INTEGER, ColumnType.FLOAT})


def load_csv(path: str | Path, delimiter: str = ",") -> tuple[list[Row], list[str]]:
    """Read a CSV into row dicts without coercing any types.

    Everything stays a string on purpose: inferring types is a separate, inspectable
    step, and a loader that guesses is a loader that guesses wrong silently.

    Args:
        path: Path to the file.
        delimiter: Field delimiter.

    Returns:
        ``(rows, column_names)``.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file has no header row.
    """
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"no such file: {source}")

    # utf-8-sig strips the byte-order mark Excel writes, which otherwise becomes part
    # of the first column's name and breaks every lookup on it.
    with source.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        if reader.fieldnames is None:
            raise ValueError(f"{source} has no header row")
        names = [name.strip() for name in reader.fieldnames]
        rows = [{name.strip(): value for name, value in row.items()} for row in reader]
    return rows, names


def numeric_values(rows: list[Row], column: str) -> list[float]:
    """Extract the parseable numeric values from a column.

    Unparseable cells are skipped rather than raising, because a mostly-numeric column
    with a stray "n/a" is the normal case and should still be summarisable.

    Args:
        rows: The table.
        column: Column name.

    Returns:
        The values that parsed as floats, in row order.
    """
    out: list[float] = []
    for row in rows:
        raw = row.get(column)
        if is_null(raw):
            continue
        try:
            out.append(float(str(raw).strip()))
        except ValueError:
            continue
    return out


@dataclass
class DatasetProfile:
    """Everything the library can say about a dataset without being told anything."""

    row_count: int
    column_count: int
    columns: dict[str, ColumnProfile] = field(default_factory=dict)
    missing: MissingReport | None = None
    summaries: dict[str, Summary] = field(default_factory=dict)
    correlations: dict[str, dict[str, float]] = field(default_factory=dict)

    @property
    def numeric_columns(self) -> list[str]:
        """Columns that could be summarised numerically, in order."""
        return [name for name, profile in self.columns.items() if profile.inferred_type in NUMERIC_TYPES]

    @property
    def categorical_columns(self) -> list[str]:
        """Columns inferred as categorical, in order."""
        return [
            name
            for name, profile in self.columns.items()
            if profile.inferred_type == ColumnType.CATEGORICAL
        ]

    @property
    def constant_columns(self) -> list[str]:
        """Columns with a single distinct value, which carry no information."""
        return [name for name, profile in self.columns.items() if profile.is_constant]

    @property
    def empty_columns(self) -> list[str]:
        """Columns that are entirely missing."""
        return [
            name for name, profile in self.columns.items() if profile.inferred_type == ColumnType.EMPTY
        ]

    def warnings(self, null_threshold: float = 0.5, correlation_threshold: float = 0.9) -> list[str]:
        """Return human-readable findings worth acting on before modelling.

        Ordered from most to least structural, because that is the order someone
        cleaning a dataset should address them in.

        Args:
            null_threshold: Flag columns at or above this null fraction.
            correlation_threshold: Flag column pairs at or above this correlation.

        Returns:
            One string per finding.
        """
        found: list[str] = []
        for name in self.empty_columns:
            found.append(f"{name}: entirely missing, drop it")
        for name in self.constant_columns:
            if name not in self.empty_columns:
                found.append(f"{name}: constant value, carries no information")
        if self.missing is not None:
            for name in self.missing.columns_above(null_threshold):
                if name in self.empty_columns:
                    continue
                fraction = self.missing.null_fractions[name]
                found.append(f"{name}: {fraction:.0%} missing, imputation may mislead")
        for left, right, value in highly_correlated_pairs(self.correlations, correlation_threshold):
            found.append(f"{left} and {right}: correlated at {value:.2f}, likely redundant")
        for name, summary in self.summaries.items():
            if summary.skew_direction == "none":
                continue
            # Normalised by IQR, not standard deviation. The standard deviation is
            # inflated by the very outliers that cause skew, so dividing by it makes
            # this test least sensitive exactly when it matters most: a column with
            # one enormous value scores as barely skewed. The IQR is unmoved by that
            # value, so the ratio stays large and the column gets flagged.
            scale = summary.iqr or summary.stdev
            if scale <= 0:
                continue
            if abs(summary.mean - summary.median) / scale > 0.5:
                found.append(
                    f"{name}: {summary.skew_direction}-skewed, the mean is a poor summary"
                )
        return found


def profile_dataset(rows: list[Row], columns: list[str] | None = None) -> DatasetProfile:
    """Profile a whole table.

    Args:
        rows: The table.
        columns: Column order; inferred from the first row when omitted.

    Returns:
        A :class:`DatasetProfile`.
    """
    if not rows:
        return DatasetProfile(row_count=0, column_count=0, missing=analyse_missing([]))

    names = columns if columns is not None else list(rows[0].keys())
    profiles = infer_schema(rows, names)

    summaries: dict[str, Summary] = {}
    numeric: dict[str, list[float]] = {}
    for name, profile in profiles.items():
        if profile.inferred_type not in NUMERIC_TYPES:
            continue
        values = numeric_values(rows, name)
        if values:
            summaries[name] = summarise(values)
            numeric[name] = values

    # Correlation needs equal-length series, and skipping nulls per column breaks that,
    # so only columns with no gaps take part.
    complete = {name: values for name, values in numeric.items() if len(values) == len(rows)}
    correlations = correlation_matrix(complete) if len(complete) > 1 else {}

    return DatasetProfile(
        row_count=len(rows),
        column_count=len(names),
        columns=profiles,
        missing=analyse_missing(rows),
        summaries=summaries,
        correlations=correlations,
    )
