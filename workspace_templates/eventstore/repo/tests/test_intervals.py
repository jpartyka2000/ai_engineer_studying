"""Confidence intervals.

The Wilson numbers below were computed from the closed form with z = 1.959963984540054
and are quoted to six decimal places in each docstring, so a failure tells you which
part of the formula moved rather than just that something did.
"""

from __future__ import annotations

import statistics

import pytest

from eventstore.perfmodel.intervals import Z_95, Interval, bootstrap_ci, wilson_interval


def test_zero_errors_in_five_requests_is_not_certainty() -> None:
    """0/5 -> [0.0, 0.434482].

    p = 0, so the spread term reduces to z * sqrt(z^2 / 4n^2) = z^2 / 2n, which is
    exactly the centre term -- the lower bound is pinned at zero and the upper bound
    is twice the centre. The normal approximation gives [0, 0] here: "we have measured
    a zero percent error rate" after five requests. That difference is the reason this
    function exists.
    """
    interval = wilson_interval(0, 5)
    assert interval.low == 0.0
    assert interval.high == pytest.approx(0.434482, abs=5e-7)


def test_a_single_error_in_a_quiet_route() -> None:
    """1/18 -> [0.009875, 0.257573], around the point estimate of 0.055556.

    The interval is wildly asymmetric around the point estimate, which is correct and
    is what the normal approximation cannot express: it would put the lower bound at
    -0.0503, below zero and unrenderable.
    """
    interval = wilson_interval(1, 18)
    assert interval.low == pytest.approx(0.009875, abs=5e-7)
    assert interval.high == pytest.approx(0.257573, abs=5e-7)
    assert interval.contains(1 / 18)


def test_a_clean_half() -> None:
    """8/16 -> [0.279996, 0.720004], symmetric about 0.5 as it must be."""
    interval = wilson_interval(8, 16)
    assert interval.low == pytest.approx(0.279996, abs=5e-7)
    assert interval.high == pytest.approx(0.720004, abs=5e-7)
    assert interval.low + interval.high == pytest.approx(1.0, abs=1e-9)


def test_bounds_stay_inside_zero_and_one_at_the_extremes() -> None:
    """5/5 -> [0.565518, 1.0], and the upper bound is exactly 1.0.

    Algebraically the upper bound at successes == trials cancels to exactly 1, but in
    floating point it lands a few ulps below, where ``min(1.0, x)`` cannot clamp it --
    a dashboard then renders 99.99999999999999%. Rounding before clamping is what
    makes this assertion an equality rather than an approximation.
    """
    assert wilson_interval(5, 5).high == 1.0
    assert wilson_interval(0, 5).low == 0.0
    for successes, trials in [(0, 1), (1, 1), (0, 300), (300, 300)]:
        interval = wilson_interval(successes, trials)
        assert 0.0 <= interval.low <= interval.high <= 1.0


def test_the_interval_narrows_as_evidence_accumulates() -> None:
    """Same proportion, more trials: 50/100 is far tighter than 5/10.

    widths: 5/10 -> 0.550..., 50/100 -> 0.192337, 500/1000 -> 0.061...
    """
    widths = [wilson_interval(n // 2, n).width for n in (10, 100, 1000)]
    assert widths[0] > widths[1] > widths[2]
    assert widths[1] == pytest.approx(0.192337, abs=5e-7)


def test_zero_trials_is_total_ignorance_not_a_measured_zero() -> None:
    """[0, 1]: before any observation, every rate is still possible."""
    assert wilson_interval(0, 0) == Interval(0.0, 1.0)


def test_impossible_counts_are_rejected() -> None:
    with pytest.raises(ValueError, match="cannot exceed"):
        wilson_interval(6, 5)
    with pytest.raises(ValueError, match="non-negative"):
        wilson_interval(-1, 5)


def test_z_95_is_the_two_sided_quantile() -> None:
    """1.96 to three places. A one-sided 1.645 here would silently halve the coverage."""
    assert Z_95 == pytest.approx(1.959964, abs=5e-7)


# ---------------------------------------------------------------------------
# bootstrap
# ---------------------------------------------------------------------------

SKEWED = [95.0, 101.0, 103.0, 110.0, 112.0, 118.0, 121.0, 130.0, 140.0, 900.0]


def test_the_same_seed_gives_the_same_interval() -> None:
    """Determinism is a contract, not a convenience.

    An interval that differs between two runs over the same data cannot be compared
    with yesterday's, cannot be put in a report, and cannot be asserted here.
    """
    first = bootstrap_ci(SKEWED, statistics.median, seed=7, resamples=500)
    second = bootstrap_ci(SKEWED, statistics.median, seed=7, resamples=500)
    assert first == second


def test_different_seeds_give_similar_but_distinct_intervals() -> None:
    """The seed must actually be used, and the interval must not depend much on it."""
    first = bootstrap_ci(SKEWED, statistics.median, seed=1, resamples=500)
    second = bootstrap_ci(SKEWED, statistics.median, seed=2, resamples=500)
    assert first != second
    assert abs(first.low - second.low) < 20.0
    assert abs(first.high - second.high) < 20.0


def test_the_interval_brackets_the_sample_statistic() -> None:
    """The median of this sample is (112 + 118) / 2 = 115.0."""
    assert statistics.median(SKEWED) == 115.0
    interval = bootstrap_ci(SKEWED, statistics.median, seed=11, resamples=1000)
    assert interval.contains(115.0)


def test_a_bigger_sample_gives_a_tighter_interval() -> None:
    """Twenty copies of the sample is twenty times the evidence for the same shape."""
    wide = bootstrap_ci(SKEWED, statistics.median, seed=3, resamples=800)
    narrow = bootstrap_ci(SKEWED * 20, statistics.median, seed=3, resamples=800)
    assert narrow.width < wide.width


def test_a_one_element_sample_has_a_zero_width_interval() -> None:
    """Every resample is identical, so there is no uncertainty to express."""
    interval = bootstrap_ci([42.0], statistics.median, seed=5, resamples=50)
    assert interval == Interval(42.0, 42.0)


def test_bootstrap_validates_its_arguments() -> None:
    with pytest.raises(ValueError, match="empty"):
        bootstrap_ci([], statistics.median, seed=1)
    with pytest.raises(ValueError, match="resamples"):
        bootstrap_ci([1.0], statistics.median, seed=1, resamples=0)
    with pytest.raises(ValueError, match="confidence"):
        bootstrap_ci([1.0], statistics.median, seed=1, confidence=1.0)


def test_seed_is_keyword_only() -> None:
    """Positional would let a caller pass the resample count as the seed by accident."""
    with pytest.raises(TypeError):
        bootstrap_ci(SKEWED, statistics.median, 7)  # type: ignore[misc]
