"""Tests for missing-value analysis and imputation.

The fit/transform split is the property under test as much as the arithmetic: an
imputer that recomputes at transform time would produce different output depending on
which batch it saw.
"""

import pytest

from edakit.missing import Imputer, Strategy, analyse_missing, fit_imputer
from edakit.schema_infer import ColumnType

ROWS = [
    {"n": "10", "m": "1.5", "k": "a"},
    {"n": "20", "m": "N/A", "k": "b"},
    {"n": "", "m": "2.5", "k": "a"},
    {"n": "30", "m": "3.5", "k": None},
]


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def test_counts_nulls_per_column():
    report = analyse_missing(ROWS)
    assert report.null_counts == {"n": 1, "m": 1, "k": 1}


def test_counts_complete_rows():
    report = analyse_missing(ROWS)
    assert report.complete_rows == 1
    assert report.completeness == pytest.approx(0.25)


def test_null_fractions():
    report = analyse_missing(ROWS)
    assert report.null_fractions["n"] == pytest.approx(0.25)


def test_columns_above_a_threshold_are_sorted():
    rows = [{"a": "", "b": "", "c": "1"}, {"a": "", "b": "1", "c": "2"}]
    report = analyse_missing(rows)
    assert report.columns_above(0.5) == ["a", "b"]


def test_an_empty_table_is_fully_complete_rather_than_a_crash():
    report = analyse_missing([])
    assert report.total_rows == 0
    assert report.completeness == 1.0
    assert report.null_fractions == {}


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------


def test_mean_is_computed_from_present_values_only():
    # 10, 20, 30 -> 20. The blank must not count as a zero.
    imputer = fit_imputer(ROWS, {"n": Strategy.MEAN}, column_types={"n": ColumnType.INTEGER})
    assert imputer.fill_values["n"] == "20"


def test_median_of_an_even_count():
    rows = [{"x": "1"}, {"x": "2"}, {"x": "3"}, {"x": "4"}]
    imputer = fit_imputer(rows, {"x": Strategy.MEDIAN})
    assert float(imputer.fill_values["x"]) == pytest.approx(2.5)


def test_an_integer_column_stays_integral_after_mean_imputation():
    """Filling must not silently turn an int column into floats."""
    rows = [{"x": "2"}, {"x": "4"}, {"x": ""}]
    imputer = fit_imputer(rows, {"x": Strategy.MEAN}, column_types={"x": ColumnType.INTEGER})
    assert imputer.fill_values["x"] == "3"


def test_mode_breaks_ties_deterministically():
    """Two values tied for most common must resolve the same way every run."""
    rows = [{"k": "b"}, {"k": "a"}, {"k": "b"}, {"k": "a"}]
    results = {fit_imputer(rows, {"k": Strategy.MODE}).fill_values["k"] for _ in range(20)}
    assert results == {"a"}


def test_constant_requires_a_constant():
    with pytest.raises(ValueError, match="no constant was given"):
        fit_imputer(ROWS, {"k": Strategy.CONSTANT})


def test_constant_is_used_as_given():
    imputer = fit_imputer(ROWS, {"k": Strategy.CONSTANT}, constants={"k": "unknown"})
    assert imputer.fill_values["k"] == "unknown"


def test_a_numeric_strategy_on_a_categorical_column_is_rejected():
    """Failing here beats failing obscurely inside float() later."""
    with pytest.raises(ValueError, match="numeric-only"):
        fit_imputer(ROWS, {"k": Strategy.MEAN}, column_types={"k": ColumnType.CATEGORICAL})


def test_a_numeric_strategy_on_unparseable_text_is_rejected():
    rows = [{"k": "apple"}, {"k": "pear"}]
    with pytest.raises(ValueError, match="not numeric"):
        fit_imputer(rows, {"k": Strategy.MEAN})


def test_an_all_null_column_learns_nothing_rather_than_inventing_a_value():
    rows = [{"x": ""}, {"x": "N/A"}]
    imputer = fit_imputer(rows, {"x": Strategy.MEAN})
    assert "x" not in imputer.fill_values


# ---------------------------------------------------------------------------
# Transforming
# ---------------------------------------------------------------------------


def test_transform_fills_only_the_missing_cells():
    imputer = fit_imputer(ROWS, {"n": Strategy.MEAN}, column_types={"n": ColumnType.INTEGER})
    filled = imputer.transform(ROWS)
    assert [row["n"] for row in filled] == ["10", "20", "20", "30"]


def test_transform_does_not_mutate_the_input():
    """A caller must be able to compare before and after."""
    imputer = fit_imputer(ROWS, {"n": Strategy.MEAN}, column_types={"n": ColumnType.INTEGER})
    before = [dict(row) for row in ROWS]
    imputer.transform(ROWS)
    assert ROWS == before


def test_drop_row_removes_rows_missing_that_column():
    imputer = fit_imputer(ROWS, {"m": Strategy.DROP_ROW})
    assert len(imputer.transform(ROWS)) == 3


def test_transform_is_a_pure_lookup_independent_of_the_batch():
    """The property that prevents train/serve skew.

    A fitted imputer applied to one row must produce the same fill as when it is
    applied to a thousand.
    """
    imputer = fit_imputer(ROWS, {"n": Strategy.MEAN}, column_types={"n": ColumnType.INTEGER})
    single = imputer.transform([{"n": "", "m": "1", "k": "a"}])
    batch = imputer.transform([{"n": "", "m": "1", "k": "a"}] * 50)
    assert single[0]["n"] == batch[0]["n"] == "20"


def test_an_unfitted_imputer_is_reported_as_such():
    assert not Imputer(strategies={}).is_fitted
