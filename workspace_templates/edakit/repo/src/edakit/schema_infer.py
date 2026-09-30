"""Infer column types from raw CSV text.

Real exports arrive as strings with no type information, and the nulls are spelled a
dozen different ways. Everything downstream -- profiling, imputation, encoding --
depends on getting this layer right, so it is deliberately explicit rather than
clever.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum

#: Spellings of "missing" seen in real exports. Compared case-insensitively after
#: stripping, so "N/A", "n/a " and "NA" all count.
NULL_TOKENS: frozenset[str] = frozenset(
    {"", "na", "n/a", "null", "none", "nil", "-", "--", "?", "nan", "missing", "unknown"}
)

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")
_BOOL_TRUE = frozenset({"true", "t", "yes", "y", "1"})
_BOOL_FALSE = frozenset({"false", "f", "no", "n", "0"})
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?")


class ColumnType(StrEnum):
    """The types this library can infer."""

    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    CATEGORICAL = "categorical"
    TEXT = "text"
    EMPTY = "empty"


#: A column with more distinct values than this fraction of its rows is text rather
#: than categorical. Encoding a free-text column as categories produces thousands of
#: useless dummy columns, which is the failure this threshold exists to prevent.
CATEGORICAL_MAX_CARDINALITY_RATIO = 0.5

#: ...but a column with few enough distinct values is categorical regardless of ratio,
#: which matters for small samples where any ratio is misleading.
CATEGORICAL_ABSOLUTE_CEILING = 20


def is_null(value: str | None) -> bool:
    """Return whether a raw cell should be treated as missing.

    Args:
        value: The raw cell text, or ``None``.

    Returns:
        Whether it is one of the recognised null spellings.
    """
    if value is None:
        return True
    return value.strip().lower() in NULL_TOKENS


def _looks_like(values: list[str], predicate) -> bool:
    """Return whether every non-null value satisfies a predicate."""
    return bool(values) and all(predicate(v) for v in values)


@dataclass
class ColumnProfile:
    """What was inferred about one column."""

    name: str
    inferred_type: ColumnType
    total_rows: int
    null_count: int
    distinct_count: int
    sample_values: list[str] = field(default_factory=list)

    @property
    def null_fraction(self) -> float:
        """Proportion of rows that were missing, 0.0 when the column is empty."""
        if self.total_rows == 0:
            return 0.0
        return self.null_count / self.total_rows

    @property
    def is_constant(self) -> bool:
        """Whether every present value is the same.

        A constant column carries no information and should usually be dropped.
        """
        return self.distinct_count == 1


def infer_column_type(values: list[str | None]) -> ColumnType:
    """Infer the type of a single column from its raw values.

    Order matters. Booleans are checked before integers because ``0``/``1`` are valid
    as both, and integers before floats because every integer also matches the float
    pattern.

    Args:
        values: Raw cell values, including nulls.

    Returns:
        The inferred :class:`ColumnType`. A column that is entirely null is
        ``EMPTY`` rather than guessed at.
    """
    present = [v.strip() for v in values if not is_null(v)]
    if not present:
        return ColumnType.EMPTY

    lowered = [v.lower() for v in present]
    if _looks_like(lowered, lambda v: v in _BOOL_TRUE or v in _BOOL_FALSE):
        return ColumnType.BOOLEAN
    if _looks_like(present, lambda v: bool(_INT_RE.match(v))):
        return ColumnType.INTEGER
    if _looks_like(present, lambda v: bool(_FLOAT_RE.match(v))):
        return ColumnType.FLOAT
    if _looks_like(present, lambda v: bool(_DATETIME_RE.match(v))):
        return ColumnType.DATETIME
    if _looks_like(present, lambda v: bool(_DATE_RE.match(v))):
        return ColumnType.DATE

    distinct = len(set(present))
    if distinct <= CATEGORICAL_ABSOLUTE_CEILING:
        return ColumnType.CATEGORICAL
    if distinct / len(present) <= CATEGORICAL_MAX_CARDINALITY_RATIO:
        return ColumnType.CATEGORICAL
    return ColumnType.TEXT


def profile_column(name: str, values: list[str | None], sample_size: int = 5) -> ColumnProfile:
    """Build a :class:`ColumnProfile` for one column.

    Args:
        name: The column name.
        values: Raw cell values, including nulls.
        sample_size: How many example values to keep.

    Returns:
        The profile.
    """
    present = [v.strip() for v in values if not is_null(v)]
    counts = Counter(present)
    return ColumnProfile(
        name=name,
        inferred_type=infer_column_type(values),
        total_rows=len(values),
        null_count=len(values) - len(present),
        distinct_count=len(counts),
        sample_values=[value for value, _ in counts.most_common(sample_size)],
    )


def infer_schema(
    rows: list[dict[str, str | None]], columns: list[str] | None = None
) -> dict[str, ColumnProfile]:
    """Profile every column in a table.

    Args:
        rows: The table as a list of row dicts, as ``csv.DictReader`` produces.
        columns: Column order. Inferred from the first row when omitted.

    Returns:
        Mapping of column name to :class:`ColumnProfile`, in column order.
    """
    if not rows:
        return {}
    names = columns if columns is not None else list(rows[0].keys())
    return {name: profile_column(name, [row.get(name) for row in rows]) for name in names}
