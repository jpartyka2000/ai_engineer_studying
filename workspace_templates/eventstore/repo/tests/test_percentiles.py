"""Percentiles.

Every expectation here is a rank, computed in the docstring, into a sample whose values
are deliberately equal to their own 1-based position. That makes the assertion and the
definition the same statement: ``percentile(1..100, 95) == 95`` is true exactly when the
rank is ``ceil(0.95 * 100) = 95``.
"""

from __future__ import annotations

import pytest

from eventstore.perfmodel.percentiles import LatencySummary, percentile, summarize


@pytest.fixture
def one_to_hundred() -> list[float]:
    """``[1.0, 2.0, ..., 100.0]``: value equals rank, so a percentile reads as its rank."""
    return [float(n) for n in range(1, 101)]


def test_percentiles_are_the_observation_at_the_ceiling_rank(one_to_hundred: list[float]) -> None:
    """n=100, so rank = ceil(q).

    p50 -> ceil(50.0) = 50 -> value 50. p95 -> 95. p99 -> 99. p100 -> 100.
    """
    assert percentile(one_to_hundred, 50) == 50.0
    assert percentile(one_to_hundred, 95) == 95.0
    assert percentile(one_to_hundred, 99) == 99.0
    assert percentile(one_to_hundred, 100) == 100.0


def test_percentile_zero_is_the_minimum(one_to_hundred: list[float]) -> None:
    """rank = ceil(0) = 0, clamped up to 1, so the smallest observation."""
    assert percentile(one_to_hundred, 0) == 1.0


def test_percentile_is_never_an_invented_value() -> None:
    """Nearest-rank, not interpolated.

    For [10, 20] the median rank is ceil(0.5 * 2) = 1, so p50 is 10 -- the lower of
    the two middle values. An interpolating definition would answer 15, which is a
    latency no request in this sample experienced.
    """
    assert percentile([10.0, 20.0], 50) == 10.0
    assert 15.0 not in {percentile([10.0, 20.0], q) for q in (0, 25, 50, 75, 100)}


def test_percentile_sorts_its_input() -> None:
    """The caller is not required to pre-sort; the result must not depend on order."""
    shuffled = [91.0, 12.0, 45.0, 7.0, 68.0]
    assert percentile(shuffled, 50) == percentile(sorted(shuffled), 50) == 45.0


def test_percentile_of_a_single_observation_is_that_observation() -> None:
    """Every rank clamps to 1 when n = 1."""
    assert percentile([42.0], 50) == 42.0
    assert percentile([42.0], 99) == 42.0


def test_percentile_rejects_an_empty_sample() -> None:
    """There is no honest answer, so there is no answer."""
    with pytest.raises(ValueError, match="empty"):
        percentile([], 50)


def test_percentile_rejects_a_q_outside_the_range() -> None:
    with pytest.raises(ValueError, match=r"\[0, 100\]"):
        percentile([1.0], 101)


def test_summarize_agrees_with_percentile(one_to_hundred: list[float]) -> None:
    """One sorted pass must produce exactly what three separate calls would.

    mean of 1..100 = 100 * 101 / 2 / 100 = 50.5.
    """
    summary = summarize(one_to_hundred)
    assert isinstance(summary, LatencySummary)
    assert summary.count == 100
    assert summary.p50 == percentile(one_to_hundred, 50) == 50.0
    assert summary.p95 == percentile(one_to_hundred, 95) == 95.0
    assert summary.p99 == percentile(one_to_hundred, 99) == 99.0
    assert summary.max == 100.0
    assert summary.mean == 50.5


def test_summarize_on_a_tiny_skewed_sample() -> None:
    """n=5, so every rank from 81 upwards is 5: p95 and p99 are both the maximum.

    ranks: p50 -> ceil(2.5) = 3 -> 30.0; p95 -> ceil(4.75) = 5 -> 900.0.
    mean = (10 + 20 + 30 + 40 + 900) / 5 = 200.0, which is larger than p50 by a factor
    of six -- the reason this service reports both.
    """
    summary = summarize([10.0, 20.0, 30.0, 40.0, 900.0])
    assert summary.p50 == 30.0
    assert summary.p95 == 900.0
    assert summary.p99 == 900.0
    assert summary.mean == 200.0


def test_summarize_rejects_an_empty_window() -> None:
    """"No traffic" must not be reported as "instantaneous"."""
    with pytest.raises(ValueError, match="empty"):
        summarize([])


def test_summary_as_dict_is_json_ready() -> None:
    payload = summarize([1.0, 2.0]).as_dict()
    assert set(payload) == {"count", "p50", "p95", "p99", "max", "mean"}
    assert all(isinstance(value, (int, float)) for value in payload.values())
