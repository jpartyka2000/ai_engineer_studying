"""Apdex.

The arithmetic is small enough to do in the docstring every time, which is the point:
an Apdex score that cannot be re-derived by hand from the bucket counts is a number
nobody can defend in a review.
"""

from __future__ import annotations

import pytest

from eventstore.perfmodel.apdex import FRUSTRATION_MULTIPLIER, apdex


def test_one_of_each_bucket() -> None:
    """T=100: 50 satisfied, 120 tolerating (<= 400), 500 frustrated (> 400).

    score = (1 + 0.5) / 3 = 0.5
    """
    score = apdex([50.0, 120.0, 500.0], 100.0)
    assert (score.satisfied, score.tolerating, score.frustrated) == (1, 1, 1)
    assert score.score == 0.5
    assert score.total == 3


def test_the_boundaries_are_inclusive_at_the_top_of_each_bucket() -> None:
    """T=100, so the frustration boundary is 4T = 400.

    Exactly 100 is satisfied, exactly 400 is tolerating, and 400.1 is frustrated.
    An exclusive boundary would move one request a whole bucket, which at the scale
    these scores are computed on is the difference between 0.93 and 0.94 -- small, and
    wrong in a way nobody would ever track down.
    """
    score = apdex([100.0, 400.0, 400.1], 100.0)
    assert (score.satisfied, score.tolerating, score.frustrated) == (1, 1, 1)


def test_tolerating_counts_at_half_weight() -> None:
    """Four tolerating requests and nothing else: (0 + 4/2) / 4 = 0.5.

    This is the whole metric. Counting a tolerating request as a success -- a request
    the user noticed -- would report 1.0 for a service that is visibly degraded for
    every single caller.
    """
    score = apdex([150.0, 200.0, 250.0, 300.0], 100.0)
    assert (score.satisfied, score.tolerating, score.frustrated) == (0, 4, 0)
    assert score.score == 0.5


def test_a_fast_service_scores_one() -> None:
    """Ten requests all under T: (10 + 0) / 10 = 1.0."""
    assert apdex([float(n) for n in range(1, 11)], 100.0).score == 1.0


def test_a_broken_service_scores_zero() -> None:
    """Three requests all over 4T: (0 + 0) / 3 = 0.0."""
    score = apdex([401.0, 900.0, 5000.0], 100.0)
    assert score.frustrated == 3
    assert score.score == 0.0


def test_a_realistic_mix() -> None:
    """T=300, ten requests: six satisfied, three tolerating, one frustrated.

    satisfied:  120, 150, 180, 240, 290, 300          -> 6
    tolerating: 310, 800, 1200 (all <= 1200 = 4T)     -> 3
    frustrated: 1201                                  -> 1
    score = (6 + 1.5) / 10 = 0.75
    """
    sample = [120.0, 150.0, 180.0, 240.0, 290.0, 300.0, 310.0, 800.0, 1200.0, 1201.0]
    score = apdex(sample, 300.0)
    assert (score.satisfied, score.tolerating, score.frustrated) == (6, 3, 1)
    assert score.score == 0.75


def test_an_empty_window_scores_one_but_says_so() -> None:
    """No request was dissatisfied because no request was made.

    The caller tells this from a real 1.0 by reading ``total``, which is why the
    bucket counts travel with the score.
    """
    score = apdex([], 100.0)
    assert score.score == 1.0
    assert score.total == 0


def test_target_must_be_positive() -> None:
    with pytest.raises(ValueError, match="target_ms"):
        apdex([1.0], 0.0)


def test_the_frustration_multiplier_is_the_specified_four() -> None:
    """Not a local tunable. Changing it makes this service's scores incomparable with
    every other team's, which is the only reason Apdex is worth reporting at all."""
    assert FRUSTRATION_MULTIPLIER == 4
