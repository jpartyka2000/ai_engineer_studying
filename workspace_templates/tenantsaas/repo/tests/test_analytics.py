"""Tests for revenue analytics.

Every expected value is hand-computed and recorded as a constant with its
derivation, so these tests verify the statistics rather than merely pinning whatever
the implementation currently returns.
"""

import pytest

from reporting.analytics import (
    Z_95,
    Interval,
    detect_change_points,
    ewma,
    month_over_month_growth,
    wilson_interval,
)

# ---------------------------------------------------------------------------
# Wilson score interval
# ---------------------------------------------------------------------------


def test_wilson_on_a_clean_half():
    """8/16 with z=1.96: centre 0.5, interval symmetric about it.

    Hand-computed: p=0.5, n=16, z^2=3.8415.
      denominator = 1 + 3.8415/16          = 1.240096
      centre      = 0.5 + 3.8415/32        = 0.620047
      spread      = 1.96*sqrt(0.25/16 + 3.8415/1024) = 1.96*sqrt(0.019376) = 0.272834
      lower = (0.620047 - 0.272834)/1.240096 = 0.280
      upper = (0.620047 + 0.272834)/1.240096 = 0.720
    """
    interval = wilson_interval(8, 16)
    assert interval.lower == pytest.approx(0.2800, abs=5e-4)
    assert interval.upper == pytest.approx(0.7200, abs=5e-4)
    # Symmetric about 0.5 at p=0.5.
    assert (interval.lower + interval.upper) / 2 == pytest.approx(0.5, abs=1e-9)


def test_wilson_stays_inside_zero_and_one_at_the_extremes():
    """The whole reason for preferring Wilson over the normal approximation."""
    assert wilson_interval(0, 10).lower == 0.0
    assert wilson_interval(10, 10).upper == 1.0
    assert 0.0 <= wilson_interval(1, 3).lower <= wilson_interval(1, 3).upper <= 1.0


def test_wilson_narrows_as_the_sample_grows():
    small = wilson_interval(5, 10)
    large = wilson_interval(500, 1000)
    assert large.width < small.width


def test_wilson_handles_an_empty_cohort():
    """A brand-new cohort must not break a dashboard."""
    assert wilson_interval(0, 0) == Interval(0.0, 0.0)


@pytest.mark.parametrize(("successes", "trials"), [(-1, 10), (11, 10)])
def test_wilson_rejects_impossible_counts(successes, trials):
    with pytest.raises(ValueError, match="successes must be within"):
        wilson_interval(successes, trials)


def test_z_95_is_the_two_sided_95_percent_value():
    assert Z_95 == pytest.approx(1.95996, abs=1e-5)


# ---------------------------------------------------------------------------
# Month-over-month growth
# ---------------------------------------------------------------------------


def test_growth_is_one_shorter_than_the_input():
    assert len(month_over_month_growth([100, 200, 300])) == 2


def test_growth_computes_the_expected_rates():
    # 100 -> 150 is +0.5; 150 -> 120 is -0.2.
    assert month_over_month_growth([100, 150, 120]) == pytest.approx([0.5, -0.2])


def test_growth_after_a_zero_month_is_zero_not_infinity():
    """Division by zero here would render as 'Infinity%' on a dashboard."""
    assert month_over_month_growth([0, 500]) == [0.0]


def test_growth_of_a_single_month_is_empty():
    assert month_over_month_growth([100]) == []
    assert month_over_month_growth([]) == []


# ---------------------------------------------------------------------------
# EWMA
# ---------------------------------------------------------------------------


def test_ewma_is_seeded_from_the_first_value():
    """Seeding from zero would drag the start of every series downward."""
    assert ewma([10, 20, 30], 0.5)[0] == 10.0


def test_ewma_matches_hand_computed_values():
    # alpha=0.5, seeded at 10:
    #   10
    #   0.5*20 + 0.5*10 = 15
    #   0.5*30 + 0.5*15 = 22.5
    assert ewma([10, 20, 30], 0.5) == pytest.approx([10.0, 15.0, 22.5])


def test_ewma_with_alpha_one_returns_the_input():
    assert ewma([3, 1, 4], 1.0) == pytest.approx([3.0, 1.0, 4.0])


def test_ewma_preserves_length():
    assert len(ewma([1, 2, 3, 4, 5], 0.3)) == 5


def test_ewma_of_an_empty_series_is_empty():
    assert ewma([], 0.5) == []


@pytest.mark.parametrize("alpha", [0.0, -0.1, 1.1])
def test_ewma_rejects_an_out_of_range_alpha(alpha):
    with pytest.raises(ValueError, match=r"alpha must be in \(0, 1\]"):
        ewma([1, 2], alpha)


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------


def test_change_detection_flags_a_spike():
    # Flat at 100, then 400: a 300% departure from the smoothed baseline.
    assert detect_change_points([100, 100, 100, 400], alpha=0.5, threshold=0.5) == [3]


def test_change_detection_ignores_noise_below_the_threshold():
    assert detect_change_points([100, 105, 98, 102], alpha=0.5, threshold=0.5) == []


def test_change_detection_never_flags_the_first_point():
    """Index 0 seeds the EWMA, so it has nothing to deviate from."""
    assert 0 not in detect_change_points([500, 100, 100], alpha=0.5, threshold=0.5)


def test_change_detection_on_a_short_series():
    assert detect_change_points([100], alpha=0.5, threshold=0.5) == []
    assert detect_change_points([], alpha=0.5, threshold=0.5) == []
