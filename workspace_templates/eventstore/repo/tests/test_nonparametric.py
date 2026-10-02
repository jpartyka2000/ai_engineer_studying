"""Mann-Whitney U.

The U statistic and the effect size are exact and are derived in each docstring from the
rank sums. The z-scores and p-values come from the tie-corrected normal approximation
with a continuity correction and are quoted to six places.
"""

from __future__ import annotations

import pytest

from eventstore.perfmodel.nonparametric import (
    MIN_SAMPLE_FOR_NORMAL_APPROX,
    mann_whitney_u,
    rank_with_ties,
)


def test_ranks_average_within_a_tie_group() -> None:
    """[10, 20, 20, 20, 30]: the three 20s occupy ranks 2, 3 and 4, averaging to 3.0.

    Averaging rather than assigning in encounter order is what makes the statistic
    independent of the input order, which matters because latencies arrive in whatever
    order the database returned them.
    """
    assert rank_with_ties([10, 20, 20, 20, 30]) == [1.0, 3.0, 3.0, 3.0, 5.0]


def test_ranks_do_not_depend_on_input_order() -> None:
    assert rank_with_ties([30, 20, 10]) == [3.0, 2.0, 1.0]


def test_complete_separation_downwards() -> None:
    """A = [1,2,3] against B = [4,5,6].

    A holds ranks 1, 2 and 3, so rank_sum_a = 6 and U = 6 - 3*4/2 = 0. No value of A
    exceeds any value of B, so the rank-biserial effect size is exactly -1.
    """
    result = mann_whitney_u([1, 2, 3], [4, 5, 6])
    assert result.u_statistic == 0.0
    assert result.effect_size == -1.0


def test_complete_separation_upwards() -> None:
    """A = [4,5,6] against B = [1,2,3]: rank_sum_a = 15, U = 15 - 6 = 9, effect = +1.

    Positive means A tends to be the slower sample. The sign convention is the one
    thing about this test worth memorising: a release comparison reads
    ``effect_size > 0`` as "the candidate is worse".
    """
    result = mann_whitney_u([4, 5, 6], [1, 2, 3])
    assert result.u_statistic == 9.0
    assert result.effect_size == 1.0


def test_interleaved_samples_show_almost_no_effect() -> None:
    """Eight pairs, alternating, A always one larger.

    U = 36 against a mean of n_a*n_b/2 = 32, giving a small positive effect of 0.125
    and p = 0.713191 -- which is the right answer. A consistent one-millisecond
    difference is real and is not worth anybody's afternoon, and the effect size is
    what says so.
    """
    result = mann_whitney_u(
        [10, 12, 14, 16, 18, 20, 22, 24], [9, 11, 13, 15, 17, 19, 21, 23]
    )
    assert result.u_statistic == 36.0
    assert result.effect_size == 0.125
    assert result.p_value == pytest.approx(0.713191, abs=5e-7)


def test_a_shifted_sample_is_detected() -> None:
    """Two n=10 ramps, the first shifted up by 20.

    U = 82 of a possible 100, effect = 2*82/100 - 1 = 0.64, z = 2.386565,
    p = 0.017007. Significant, and the effect size is large enough to act on.
    """
    result = mann_whitney_u(
        [120, 125, 130, 135, 140, 145, 150, 155, 160, 165],
        [100, 105, 110, 115, 120, 125, 130, 135, 140, 145],
    )
    assert result.u_statistic == 82.0
    assert result.effect_size == pytest.approx(0.64)
    assert result.z_score == pytest.approx(2.386565, abs=5e-7)
    assert result.p_value == pytest.approx(0.017007, abs=5e-7)
    assert result.approximation_valid is True


def test_the_tie_correction_is_applied() -> None:
    """Heavy ties: latencies recorded in whole milliseconds repeat constantly.

    Pooled, this pair has three tie groups -- five 100s, six 200s and five 300s -- so
    the correction term sum(t^3 - t) is 120 + 210 + 120 = 450. With n = 16 and
    n_a*n_b = 64 the variance drops from (64/12)*17 = 90.666667 to
    (64/12)*(17 - 450/240) = 80.666667, and the z-score moves from -0.525108 to
    **-0.556702**: further from zero, not closer.

    This is why the correction is not optional. Without it the variance is overstated,
    every z is pulled towards zero, and a real regression in a sample full of repeated
    millisecond values is reported as noise.
    """
    result = mann_whitney_u(
        [100, 100, 100, 200, 200, 200, 300, 300],
        [100, 100, 200, 200, 200, 300, 300, 300],
    )
    assert result.u_statistic == 26.5
    assert result.z_score == pytest.approx(-0.556702, abs=5e-7)
    assert abs(result.z_score) > 0.525108


def test_two_identical_samples_have_nothing_to_report() -> None:
    """Every observation is 5, so the variance is zero and the test must not divide by it."""
    result = mann_whitney_u([5] * 6, [5] * 6)
    assert result.z_score == 0.0
    assert result.p_value == 1.0
    assert result.effect_size == 0.0


def test_small_samples_are_flagged_rather_than_quoted() -> None:
    """Three against three is below the threshold, so the p-value must not be trusted.

    The result still carries an effect size, because that part is exact.
    """
    result = mann_whitney_u([1, 2, 3], [4, 5, 6])
    assert result.approximation_valid is False
    assert MIN_SAMPLE_FOR_NORMAL_APPROX == 8

    big = mann_whitney_u(list(range(8)), list(range(8, 16)))
    assert big.approximation_valid is True


def test_empty_samples_are_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        mann_whitney_u([], [1, 2])
    with pytest.raises(ValueError, match="non-empty"):
        mann_whitney_u([1, 2], [])


def test_p_value_stays_in_range() -> None:
    """A continuity correction that overshoots could push a p-value past 1.0."""
    for a, b in [([1], [1]), ([1], [2]), ([1, 1], [1, 2])]:
        assert 0.0 <= mann_whitney_u(a, b).p_value <= 1.0
