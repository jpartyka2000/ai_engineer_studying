"""Tests for outlier detection, scaling and encoding.

Numeric expectations are hand-computed, with the derivation in the docstring, so these
verify the maths rather than pinning whatever the code currently returns.
"""

import pytest

from edakit.encode import (
    MISSING_LABEL,
    OTHER_LABEL,
    UnseenPolicy,
    fit_one_hot,
    fit_ordinal,
)
from edakit.outliers import Method, detect_outliers, quantile, winsorize
from edakit.scale import ScalerKind, fit_scaler

# ---------------------------------------------------------------------------
# Quantiles
# ---------------------------------------------------------------------------


def test_quantile_endpoints():
    values = [1.0, 2.0, 3.0, 4.0]
    assert quantile(values, 0.0) == 1.0
    assert quantile(values, 1.0) == 4.0


def test_quantile_interpolates():
    """[1,2,3,4] at q=0.25: position = 0.25*3 = 0.75, so 1 + 0.75*(2-1) = 1.75."""
    assert quantile([1.0, 2.0, 3.0, 4.0], 0.25) == pytest.approx(1.75)


def test_quantile_of_a_single_value():
    assert quantile([7.0], 0.5) == 7.0


def test_quantile_rejects_an_empty_series():
    with pytest.raises(ValueError, match="empty series"):
        quantile([], 0.5)


@pytest.mark.parametrize("q", [-0.1, 1.1])
def test_quantile_rejects_out_of_range(q):
    with pytest.raises(ValueError, match=r"q must be in \[0, 1\]"):
        quantile([1.0, 2.0], q)


# ---------------------------------------------------------------------------
# Outliers
# ---------------------------------------------------------------------------


def test_iqr_flags_an_extreme_value():
    values = [10, 11, 12, 13, 14, 15, 1000]
    report = detect_outliers(values, Method.IQR)
    assert report.indices == (6,)


def test_iqr_bounds_are_hand_computable():
    """[1..8]: q1 = 2.75, q3 = 6.25, IQR = 3.5, so bounds are -2.5 and 11.5."""
    report = detect_outliers([1, 2, 3, 4, 5, 6, 7, 8], Method.IQR)
    assert report.lower_bound == pytest.approx(-2.5)
    assert report.upper_bound == pytest.approx(11.5)
    assert report.indices == ()


def test_zscore_is_dragged_by_the_outlier_it_hunts():
    """The documented weakness: one huge value inflates the standard deviation.

    IQR flags the 1000 here; the z-score method does not, because the 1000 has made
    the spread wide enough to contain itself.
    """
    values = [10, 11, 12, 13, 14, 15, 1000]
    assert detect_outliers(values, Method.IQR).count == 1
    assert detect_outliers(values, Method.ZSCORE).count == 0


def test_modified_zscore_is_robust_where_zscore_is_not():
    values = [10, 11, 12, 13, 14, 15, 1000]
    assert detect_outliers(values, Method.MODIFIED_ZSCORE).count == 1


def test_a_constant_series_has_no_outliers():
    """Nothing can be unusual when everything is identical."""
    report = detect_outliers([5.0] * 10, Method.ZSCORE)
    assert report.count == 0
    assert report.lower_bound is None


def test_a_series_shorter_than_three_is_never_flagged():
    """With two points any notion of 'unusual' is noise."""
    assert detect_outliers([1.0, 1000.0], Method.IQR).count == 0


def test_fraction_of_an_empty_series_is_zero():
    assert detect_outliers([], Method.IQR).fraction == 0.0


def test_winsorize_clamps_rather_than_drops():
    values = [10, 11, 12, 13, 14, 15, 1000]
    report = detect_outliers(values, Method.IQR)
    clamped = winsorize(values, report)
    assert len(clamped) == len(values)
    assert clamped[-1] == pytest.approx(report.upper_bound)


def test_winsorize_is_a_noop_without_bounds():
    report = detect_outliers([1.0, 2.0], Method.IQR)
    assert winsorize([1.0, 2.0], report) == [1.0, 2.0]


# ---------------------------------------------------------------------------
# Scaling
# ---------------------------------------------------------------------------


def test_standard_scaler_centres_and_scales():
    """[2,4,4,4,5,5,7,9]: mean 5, population sd 2, so 9 maps to 2.0."""
    scaler = fit_scaler([2, 4, 4, 4, 5, 5, 7, 9], ScalerKind.STANDARD)
    assert scaler.centre == pytest.approx(5.0)
    assert scaler.spread == pytest.approx(2.0)
    assert scaler.transform([9])[0] == pytest.approx(2.0)


def test_minmax_maps_to_zero_and_one():
    scaler = fit_scaler([10, 20, 30], ScalerKind.MINMAX)
    assert scaler.transform([10, 20, 30]) == pytest.approx([0.0, 0.5, 1.0])


def test_robust_scaler_ignores_an_extreme_value():
    """Median and IQR barely move when one value is enormous."""
    ordinary = fit_scaler([1, 2, 3, 4, 5], ScalerKind.ROBUST)
    with_outlier = fit_scaler([1, 2, 3, 4, 5, 10_000], ScalerKind.ROBUST)
    assert abs(with_outlier.centre - ordinary.centre) < 1.0


def test_a_constant_column_scales_to_zeros_rather_than_dividing_by_zero():
    scaler = fit_scaler([7.0] * 5, ScalerKind.STANDARD)
    assert scaler.spread == 1.0
    assert scaler.transform([7.0, 7.0]) == [0.0, 0.0]


def test_inverse_transform_round_trips():
    scaler = fit_scaler([1, 5, 9, 13], ScalerKind.STANDARD)
    original = [1.0, 5.0, 9.0, 13.0]
    assert scaler.inverse_transform(scaler.transform(original)) == pytest.approx(original)


def test_fit_rejects_an_empty_series():
    with pytest.raises(ValueError, match="empty series"):
        fit_scaler([], ScalerKind.STANDARD)


def test_transform_is_independent_of_the_batch():
    """One row must scale the same as the same row inside a batch."""
    scaler = fit_scaler([0, 10, 20, 30], ScalerKind.MINMAX)
    assert scaler.transform([15])[0] == scaler.transform([15] * 100)[0]


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------


def test_one_hot_columns_are_sorted_and_stable():
    encoder = fit_one_hot(["team", "free", "enterprise", "team"])
    assert encoder.column_names[:3] == ["enterprise", "free", "team"]


def test_one_hot_always_has_a_missing_bucket():
    encoder = fit_one_hot(["a", "b"])
    assert MISSING_LABEL in encoder.column_names
    assert encoder.transform_one(None)[encoder.column_names.index(MISSING_LABEL)] == 1


def test_one_hot_width_is_fixed_by_fit():
    """The consumer's column count must not depend on what transform happens to see."""
    encoder = fit_one_hot(["a", "b"])
    for value in ["a", "b", "zzz", None, ""]:
        assert len(encoder.transform_one(value)) == encoder.width


def test_unseen_category_goes_to_other_by_default():
    encoder = fit_one_hot(["a", "b"])
    vector = encoder.transform_one("zzz")
    assert vector[encoder.column_names.index(OTHER_LABEL)] == 1


def test_unseen_category_can_raise():
    encoder = fit_one_hot(["a", "b"], unseen_policy=UnseenPolicy.ERROR)
    with pytest.raises(ValueError, match="unseen category"):
        encoder.transform_one("zzz")


def test_unseen_category_can_encode_as_all_zeros():
    encoder = fit_one_hot(["a", "b"], unseen_policy=UnseenPolicy.ZERO)
    assert sum(encoder.transform_one("zzz")) == 0


def test_max_categories_folds_the_rare_tail():
    values = ["a"] * 10 + ["b"] * 8 + ["c"] * 2 + ["d"] * 1
    encoder = fit_one_hot(values, max_categories=2)
    assert encoder.categories == ["a", "b"]
    assert encoder.unseen_policy == UnseenPolicy.OTHER
    assert encoder.transform_one("c")[encoder.column_names.index(OTHER_LABEL)] == 1


def test_ordinal_respects_an_explicit_order():
    encoder = fit_ordinal([], order=["free", "team", "enterprise"])
    assert encoder.transform(["free", "team", "enterprise"]) == [0, 1, 2]


def test_ordinal_falls_back_to_alphabetical():
    encoder = fit_ordinal(["team", "free", "enterprise"])
    assert encoder.transform(["enterprise", "free", "team"]) == [0, 1, 2]


def test_ordinal_maps_unknown_and_missing_to_the_sentinel():
    encoder = fit_ordinal([], order=["low", "high"])
    assert encoder.transform(["nope", None, ""]) == [-1, -1, -1]
