"""Tests for loading, correlation, whole-dataset profiling and reporting.

These run against the real messy CSVs in ``datasets/``, so they exercise the unicode,
mixed null spellings and outliers a synthetic fixture would let through.
"""

from pathlib import Path

import pytest

from edakit.corr import correlation_matrix, highly_correlated_pairs, pearson, spearman, summarise
from edakit.profile import load_csv, numeric_values, profile_dataset
from edakit.report import render_markdown, render_text
from edakit.schema_infer import ColumnType

DATASETS = Path(__file__).resolve().parent.parent / "datasets"

# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def test_load_keeps_everything_as_strings():
    """A loader that guesses types is a loader that guesses wrong silently."""
    rows, _ = load_csv(DATASETS / "tiny.csv")
    assert rows[0]["a"] == "1"
    assert isinstance(rows[0]["a"], str)


def test_load_reports_column_order():
    _, columns = load_csv(DATASETS / "tiny.csv")
    assert columns == ["a", "b", "c"]


def test_load_handles_unicode_names():
    rows, _ = load_csv(DATASETS / "customers.csv")
    names = {row["name"] for row in rows}
    assert "Ana Sørensen" in names
    assert "Dieter Müller" in names


def test_load_rejects_a_missing_file():
    with pytest.raises(FileNotFoundError, match="no such file"):
        load_csv(DATASETS / "does-not-exist.csv")


def test_numeric_values_skips_unparseable_cells():
    """A mostly-numeric column with a stray 'N/A' must still be summarisable."""
    rows, _ = load_csv(DATASETS / "customers.csv")
    seats = numeric_values(rows, "seats")
    assert len(seats) < len(rows)
    assert all(isinstance(value, float) for value in seats)


# ---------------------------------------------------------------------------
# Correlation
# ---------------------------------------------------------------------------


def test_pearson_of_a_perfect_line_is_one():
    assert pearson([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)


def test_pearson_of_an_inverse_line_is_minus_one():
    assert pearson([1, 2, 3, 4], [8, 6, 4, 2]) == pytest.approx(-1.0)


def test_pearson_of_a_constant_series_is_zero_not_nan():
    """Undefined mathematically; 0.0 is the reading that will not mislead a heatmap."""
    assert pearson([1, 2, 3], [5, 5, 5]) == 0.0


def test_pearson_stays_within_bounds():
    """Accumulated float error can otherwise nudge a perfect correlation past 1.0."""
    assert -1.0 <= pearson([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) <= 1.0


def test_pearson_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="same length"):
        pearson([1, 2], [1, 2, 3])


def test_pearson_needs_two_points():
    with pytest.raises(ValueError, match="at least two points"):
        pearson([1], [1])


def test_spearman_sees_a_monotonic_curve_that_pearson_underrates():
    xs = [1, 2, 3, 4, 5]
    ys = [1, 4, 9, 16, 25]
    assert spearman(xs, ys) == pytest.approx(1.0)
    assert pearson(xs, ys) < 1.0


def test_spearman_handles_ties_by_averaging_ranks():
    assert spearman([1, 2, 2, 3], [1, 2, 2, 3]) == pytest.approx(1.0)


def test_correlation_matrix_is_symmetric_with_a_unit_diagonal():
    matrix = correlation_matrix({"a": [1, 2, 3], "b": [3, 2, 1]})
    assert matrix["a"]["a"] == 1.0
    assert matrix["a"]["b"] == pytest.approx(matrix["b"]["a"])


def test_correlation_matrix_keys_are_sorted():
    matrix = correlation_matrix({"z": [1, 2], "a": [2, 1]})
    assert list(matrix) == ["a", "z"]


def test_correlation_matrix_rejects_an_unknown_method():
    with pytest.raises(ValueError, match="unknown method"):
        correlation_matrix({"a": [1, 2]}, method="kendall")


def test_highly_correlated_pairs_reports_each_pair_once():
    matrix = correlation_matrix({"a": [1, 2, 3], "b": [2, 4, 6], "c": [5, 1, 9]})
    pairs = highly_correlated_pairs(matrix, threshold=0.9)
    assert len(pairs) == 1
    assert pairs[0][:2] == ("a", "b")


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------


def test_summary_values_are_hand_computable():
    """[2,4,4,4,5,5,7,9]: mean 5, median 4.5, population sd 2."""
    summary = summarise([2, 4, 4, 4, 5, 5, 7, 9])
    assert summary.mean == pytest.approx(5.0)
    assert summary.median == pytest.approx(4.5)
    assert summary.stdev == pytest.approx(2.0)
    assert summary.minimum == 2
    assert summary.maximum == 9


def test_summary_detects_right_skew():
    summary = summarise([1, 1, 1, 2, 2, 50])
    assert summary.skew_direction == "right"


def test_summary_of_a_symmetric_series_has_no_skew():
    assert summarise([1, 2, 3]).skew_direction == "none"


def test_summary_of_one_value_has_zero_spread():
    summary = summarise([5.0])
    assert summary.stdev == 0.0
    assert summary.iqr == 0.0


def test_summary_rejects_an_empty_series():
    with pytest.raises(ValueError, match="empty series"):
        summarise([])


# ---------------------------------------------------------------------------
# Whole-dataset profile, against the real messy data
# ---------------------------------------------------------------------------


@pytest.fixture
def customers():
    rows, columns = load_csv(DATASETS / "customers.csv")
    return profile_dataset(rows, columns)


def test_profile_counts_rows_and_columns(customers):
    assert customers.row_count == 30
    assert customers.column_count == 11


def test_profile_finds_the_entirely_empty_column(customers):
    assert "legacy_field" in customers.empty_columns


def test_profile_classifies_the_plan_column_as_categorical(customers):
    assert customers.columns["plan"].inferred_type == ColumnType.CATEGORICAL


def test_profile_treats_mixed_nulls_in_seats_as_missing(customers):
    """seats contains '', 'N/A', 'none' and '-' -- all four must count as missing."""
    assert customers.columns["seats"].null_count == 4


def test_profile_warns_about_the_empty_column(customers):
    assert any("legacy_field" in warning for warning in customers.warnings())


def test_profile_warns_about_the_skewed_spend_column(customers):
    """One 999999 entry makes monthly_spend badly right-skewed."""
    assert any("monthly_spend" in w and "skew" in w for w in customers.warnings())


def test_profile_of_an_empty_table_does_not_crash():
    profile = profile_dataset([])
    assert profile.row_count == 0
    assert profile.warnings() == []


def test_numeric_and_categorical_columns_are_disjoint(customers):
    assert not set(customers.numeric_columns) & set(customers.categorical_columns)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def test_text_report_mentions_every_column(customers):
    report = render_text(customers)
    for name in customers.columns:
        assert name in report


def test_text_report_includes_a_findings_section(customers):
    assert "FINDINGS" in render_text(customers)


def test_markdown_report_is_a_table(customers):
    report = render_markdown(customers)
    assert "| column | type | nulls | distinct |" in report
    assert "# Dataset profile" in report


def test_reports_render_for_an_empty_dataset():
    profile = profile_dataset([])
    assert render_text(profile)
    assert render_markdown(profile)
