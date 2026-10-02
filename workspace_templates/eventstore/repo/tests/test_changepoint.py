"""EWMA and CUSUM, and the cases that tell them apart.

Both series below are exact: the in-control points are exactly the target and the
out-of-control points are exactly a whole number of sigma away, so every value of both
statistics can be worked out on paper. That is deliberate. The difference between these
two detectors is the kind of thing that gets argued about with intuitions, and the two
tests that matter here settle it with arithmetic.
"""

from __future__ import annotations

import pytest

from eventstore.perfmodel.changepoint import (
    DEFAULT_ALPHA,
    DEFAULT_DECISION_H,
    DEFAULT_SLACK_K,
    cusum_detect,
    ewma_detect,
)

TARGET = 100.0
SIGMA = 10.0

#: Thirty points exactly on target, then thirty exactly one sigma above it. This is the
#: shape of a deploy regression: nothing about any single observation is remarkable.
STEP_SHIFT = [TARGET] * 30 + [TARGET + SIGMA] * 30

#: One five-sigma observation in an otherwise perfect series. This is the shape of an
#: incident: one terrible minute, then recovery.
LONE_SPIKE = [TARGET] * 10 + [TARGET + 5 * SIGMA] + [TARGET] * 19


def test_neither_detector_alarms_on_a_perfect_series() -> None:
    """Sixty observations exactly on target. A false alarm here is an alarm on nothing."""
    flat = [TARGET] * 60
    assert cusum_detect(flat, target=TARGET, sigma=SIGMA).alarmed is False
    assert ewma_detect(flat, target=TARGET, sigma=SIGMA).alarmed is False


def test_cusum_catches_a_one_sigma_sustained_shift_at_index_40() -> None:
    """The arithmetic, exactly.

    Before the shift every standardised deviation is 0, so ``max(0, 0 - k)`` keeps the
    accumulator pinned at zero. After it, each observation contributes
    ``1.0 - k = 0.5``, so after i post-shift points the statistic is ``0.5 * i``. It
    first exceeds ``h = 5`` at ``i = 11``, which is index ``30 + 10 = 40``, where the
    statistic is exactly 5.5.

    Eleven minutes to notice a regression that no single observation reveals.
    """
    result = cusum_detect(STEP_SHIFT, target=TARGET, sigma=SIGMA)
    assert result.alarmed is True
    assert result.index == 40
    assert result.statistic[40] == pytest.approx(5.5)
    assert result.statistic[29] == 0.0


def test_ewma_never_catches_that_shift_at_all() -> None:
    """The same series, and the reason the two detectors are not interchangeable.

    The weighted mean converges geometrically to the new level, so it approaches
    110 and no further -- a deviation of 10, i.e. one sigma. The control band settles
    at ``3 * sigma * sqrt(alpha / (2 - alpha))`` = ``30 * sqrt(0.3/1.7)`` = 12.6025.
    Ten is less than 12.6025, so the statistic never leaves the band: not late, never.

    An EWMA chart watching a deploy for a one-sigma regression reports "no change"
    for as long as you care to leave it running.
    """
    result = ewma_detect(STEP_SHIFT, target=TARGET, sigma=SIGMA)
    assert result.alarmed is False
    assert result.index is None
    assert max(abs(value - TARGET) for value in result.statistic) == pytest.approx(10.0, abs=1e-3)
    assert result.limit == pytest.approx(12.6025, abs=1e-4)


def test_ewma_catches_a_lone_spike_that_cusum_absorbs() -> None:
    """The converse, so neither detector looks strictly better than the other.

    One five-sigma point moves the weighted mean to ``0.3*150 + 0.7*100 = 115``, a
    deviation of 15 against a band of 12.6025, so EWMA alarms immediately at index 10.
    CUSUM slashes the same observation by ``k`` and accumulates ``5 - 0.5 = 4.5``,
    which is under ``h = 5``; the series then returns to target and the accumulator
    decays back to zero. CUSUM never alarms.

    EWMA for incidents, CUSUM for deploys. That is the rule this service follows.
    """
    ewma = ewma_detect(LONE_SPIKE, target=TARGET, sigma=SIGMA)
    assert ewma.alarmed is True
    assert ewma.index == 10
    assert ewma.statistic[10] == pytest.approx(115.0)

    cusum = cusum_detect(LONE_SPIKE, target=TARGET, sigma=SIGMA)
    assert cusum.alarmed is False
    assert max(cusum.statistic) == pytest.approx(4.5)


def test_cusum_is_two_sided() -> None:
    """A service that suddenly got faster is also a change worth knowing about.

    Often it means it stopped doing something -- a cache serving stale results, a
    downstream call that is now failing fast.
    """
    downward = [TARGET] * 10 + [TARGET - SIGMA] * 30
    result = cusum_detect(downward, target=TARGET, sigma=SIGMA)
    assert result.alarmed is True
    assert result.index == 20


def test_the_statistic_is_reported_for_every_observation() -> None:
    """An alarm has to be explainable to whoever it wakes up."""
    result = cusum_detect(STEP_SHIFT, target=TARGET, sigma=SIGMA)
    assert len(result.statistic) == len(STEP_SHIFT)
    assert len(ewma_detect(STEP_SHIFT, target=TARGET, sigma=SIGMA).statistic) == len(STEP_SHIFT)


def test_empty_series_do_not_alarm() -> None:
    assert cusum_detect([], target=TARGET, sigma=SIGMA).alarmed is False
    assert ewma_detect([], target=TARGET, sigma=SIGMA).alarmed is False


def test_detectors_validate_their_parameters() -> None:
    with pytest.raises(ValueError, match="sigma"):
        cusum_detect([1.0], target=0.0, sigma=0.0)
    with pytest.raises(ValueError, match="sigma"):
        ewma_detect([1.0], target=0.0, sigma=-1.0)
    with pytest.raises(ValueError, match="alpha"):
        ewma_detect([1.0], target=0.0, sigma=1.0, alpha=0.0)
    with pytest.raises(ValueError, match="decision_h"):
        cusum_detect([1.0], target=0.0, sigma=1.0, decision_h=0.0)


def test_the_default_tuning_is_the_textbook_pairing() -> None:
    """k = 0.5 with h = 5 is tuned to detect a one-sigma shift; alpha = 0.3 with L = 3
    is an ordinary EWMA chart. Changing any of them changes what every historical
    alarm meant, so they are constants with comments rather than configuration."""
    assert (DEFAULT_SLACK_K, DEFAULT_DECISION_H) == (0.5, 5.0)
    assert DEFAULT_ALPHA == 0.3
