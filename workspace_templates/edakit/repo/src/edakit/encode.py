"""Categorical encoding.

The recurring hazard here is a category appearing at transform time that was not
present at fit time. Every encoder in this module has an explicit, documented answer
for that case, because the default behaviour of silently producing a different number
of columns breaks whatever consumes the output.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum

from edakit.schema_infer import is_null

#: Column name suffix for the bucket that collects unseen categories.
OTHER_LABEL = "__other__"
#: Column name suffix for rows whose value was missing.
MISSING_LABEL = "__missing__"


class UnseenPolicy(StrEnum):
    """What to do when transform meets a category that fit never saw."""

    OTHER = "other"
    ERROR = "error"
    ZERO = "zero"


@dataclass
class OneHotEncoder:
    """A fitted one-hot encoder.

    Attributes:
        categories: The categories learned at fit time, in sorted order so the output
            column order is stable across runs.
        unseen_policy: How to handle categories not seen at fit time.
    """

    categories: list[str]
    unseen_policy: UnseenPolicy = UnseenPolicy.OTHER

    @property
    def column_names(self) -> list[str]:
        """The output columns, in order.

        Always includes the missing bucket, and the other bucket when the policy uses
        it, so the width is fixed by fit and cannot vary with the input.
        """
        names = list(self.categories) + [MISSING_LABEL]
        if self.unseen_policy == UnseenPolicy.OTHER:
            names.append(OTHER_LABEL)
        return names

    @property
    def width(self) -> int:
        """Number of output columns."""
        return len(self.column_names)

    def transform_one(self, value: str | None) -> list[int]:
        """Encode a single value.

        Args:
            value: The raw value.

        Returns:
            A list of 0/1 of length :attr:`width`.

        Raises:
            ValueError: If the value is unseen and the policy is ``ERROR``.
        """
        names = self.column_names
        vector = [0] * len(names)

        if is_null(value):
            vector[names.index(MISSING_LABEL)] = 1
            return vector

        cleaned = str(value).strip()
        if cleaned in self.categories:
            vector[names.index(cleaned)] = 1
            return vector

        if self.unseen_policy == UnseenPolicy.ERROR:
            raise ValueError(f"unseen category {cleaned!r}; known: {self.categories}")
        if self.unseen_policy == UnseenPolicy.OTHER:
            vector[names.index(OTHER_LABEL)] = 1
        # ZERO: leave the vector all zeros, which is a deliberate signal of "none of
        # the known categories" rather than a silent misclassification.
        return vector

    def transform(self, values: list[str | None]) -> list[list[int]]:
        """Encode a column."""
        return [self.transform_one(value) for value in values]


def fit_one_hot(
    values: list[str | None],
    unseen_policy: UnseenPolicy = UnseenPolicy.OTHER,
    max_categories: int | None = None,
) -> OneHotEncoder:
    """Learn one-hot categories from a column.

    Args:
        values: The column to fit on.
        unseen_policy: How transform should handle unknown categories.
        max_categories: Keep only the most frequent N, folding the rest into the
            other bucket. High-cardinality columns otherwise produce thousands of
            near-empty columns.

    Returns:
        A fitted :class:`OneHotEncoder`.
    """
    counts = Counter(str(v).strip() for v in values if not is_null(v))
    if max_categories is not None and len(counts) > max_categories:
        # Sort by descending count then by name, so ties are broken deterministically
        # rather than by insertion order.
        kept = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:max_categories]
        categories = sorted(name for name, _ in kept)
        # Folding requires a bucket to fold into.
        unseen_policy = UnseenPolicy.OTHER
    else:
        categories = sorted(counts)
    return OneHotEncoder(categories=categories, unseen_policy=unseen_policy)


@dataclass
class OrdinalEncoder:
    """A fitted ordinal encoder, mapping categories to integers.

    Only appropriate when the categories genuinely have an order. Using it on
    unordered categories tells a model that ``c > b > a``, which is a claim about the
    data that is usually false.
    """

    mapping: dict[str, int] = field(default_factory=dict)
    unseen_value: int = -1

    def transform_one(self, value: str | None) -> int:
        """Encode a single value, returning :attr:`unseen_value` for unknowns."""
        if is_null(value):
            return self.unseen_value
        return self.mapping.get(str(value).strip(), self.unseen_value)

    def transform(self, values: list[str | None]) -> list[int]:
        """Encode a column."""
        return [self.transform_one(value) for value in values]


def fit_ordinal(values: list[str | None], order: list[str] | None = None) -> OrdinalEncoder:
    """Learn an ordinal mapping.

    Args:
        values: The column to fit on.
        order: Explicit category order, lowest first. When omitted the categories are
            sorted alphabetically, which is almost never the meaningful order -- so
            pass it whenever the order matters.

    Returns:
        A fitted :class:`OrdinalEncoder`.
    """
    if order is not None:
        return OrdinalEncoder(mapping={name: index for index, name in enumerate(order)})
    categories = sorted({str(v).strip() for v in values if not is_null(v)})
    return OrdinalEncoder(mapping={name: index for index, name in enumerate(categories)})
