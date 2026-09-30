"""Tests for type inference and null detection.

This is the foundation layer: profiling, imputation and encoding all trust it, so its
edge cases are spelled out rather than assumed.
"""

import pytest

from edakit.schema_infer import (
    ColumnType,
    infer_column_type,
    infer_schema,
    is_null,
    profile_column,
)

# ---------------------------------------------------------------------------
# Null detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["", " ", "NA", "na", "N/A", "n/a ", "NULL", "null", "None", "-", "--", "?", "nan", "unknown"],
)
def test_recognised_null_spellings(value):
    """Real exports spell missing a dozen different ways."""
    assert is_null(value)


def test_none_is_null():
    assert is_null(None)


@pytest.mark.parametrize("value", ["0", "false", "no", "n", "nada", "N.A.", "not applicable"])
def test_values_that_are_not_null(value):
    """`0` and `false` are data, not absence -- conflating them corrupts every total."""
    assert not is_null(value)


# ---------------------------------------------------------------------------
# Type inference
# ---------------------------------------------------------------------------


def test_integers():
    assert infer_column_type(["1", "2", "-3", "+4"]) == ColumnType.INTEGER


def test_floats():
    assert infer_column_type(["1.5", "2.0", "-0.25", "1e3"]) == ColumnType.FLOAT


def test_a_mix_of_ints_and_floats_is_float():
    """Widening to float is safe; narrowing to int would lose the decimals."""
    assert infer_column_type(["1", "2.5", "3"]) == ColumnType.FLOAT


def test_booleans_win_over_integers():
    """`0`/`1` parse as both, and boolean is the more specific reading."""
    assert infer_column_type(["0", "1", "1", "0"]) == ColumnType.BOOLEAN


@pytest.mark.parametrize(
    "values",
    [["true", "false"], ["TRUE", "FALSE"], ["yes", "no"], ["t", "f"], ["Y", "N"]],
)
def test_boolean_spellings(values):
    assert infer_column_type(values) == ColumnType.BOOLEAN


def test_dates():
    assert infer_column_type(["2025-01-01", "2025-12-31"]) == ColumnType.DATE


def test_datetimes():
    assert infer_column_type(["2025-01-01T08:15:00", "2025-01-02 09:00"]) == ColumnType.DATETIME


def test_low_cardinality_strings_are_categorical():
    assert infer_column_type(["free", "team", "enterprise"] * 20) == ColumnType.CATEGORICAL


def test_high_cardinality_strings_are_text():
    """Encoding free text as categories yields thousands of useless columns."""
    values = [f"a unique sentence number {n}" for n in range(60)]
    assert infer_column_type(values) == ColumnType.TEXT


def test_a_small_sample_of_distinct_strings_is_still_categorical():
    """Below the absolute ceiling, ratio-based reasoning is misleading."""
    assert infer_column_type(["alpha", "beta", "gamma"]) == ColumnType.CATEGORICAL


def test_an_all_null_column_is_empty_not_guessed():
    assert infer_column_type(["", "NA", None, "null"]) == ColumnType.EMPTY


def test_nulls_do_not_change_the_inferred_type():
    """A stray `n/a` in a numeric column must not make it text."""
    assert infer_column_type(["1", "N/A", "3", ""]) == ColumnType.INTEGER


def test_whitespace_is_stripped_before_inference():
    assert infer_column_type([" 1 ", "2  ", " 3"]) == ColumnType.INTEGER


# ---------------------------------------------------------------------------
# Column profiles
# ---------------------------------------------------------------------------


def test_profile_counts_nulls_and_distinct():
    profile = profile_column("plan", ["free", "team", "free", "N/A", None])
    assert profile.total_rows == 5
    assert profile.null_count == 2
    assert profile.distinct_count == 2
    assert profile.null_fraction == pytest.approx(0.4)


def test_profile_detects_a_constant_column():
    assert profile_column("x", ["a", "a", "a"]).is_constant


def test_profile_of_an_empty_column_has_zero_null_fraction_not_a_crash():
    assert profile_column("x", []).null_fraction == 0.0


def test_profile_keeps_the_most_common_samples():
    profile = profile_column("k", ["a"] * 5 + ["b"] * 3 + ["c"], sample_size=2)
    assert profile.sample_values == ["a", "b"]


# ---------------------------------------------------------------------------
# Whole-table schema
# ---------------------------------------------------------------------------


def test_infer_schema_covers_every_column_in_order():
    rows = [{"a": "1", "b": "x"}, {"a": "2", "b": "y"}]
    schema = infer_schema(rows)
    assert list(schema) == ["a", "b"]
    assert schema["a"].inferred_type == ColumnType.INTEGER
    assert schema["b"].inferred_type == ColumnType.CATEGORICAL


def test_infer_schema_of_an_empty_table_is_empty():
    assert infer_schema([]) == {}


def test_infer_schema_respects_an_explicit_column_order():
    rows = [{"a": "1", "b": "2"}]
    assert list(infer_schema(rows, ["b", "a"])) == ["b", "a"]
