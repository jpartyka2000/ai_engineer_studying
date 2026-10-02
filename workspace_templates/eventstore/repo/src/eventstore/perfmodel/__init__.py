"""The performance model: the statistics this service reports.

Everything in here is a **pure function of numbers**. No module in this package imports
``mongo``, ``duck`` or ``api``, and that is deliberate -- it means every statistic can be
tested against a hand-computed constant rather than against whatever happens to be in the
database today, and it means a statistic can be reviewed by someone who does not know
where the data came from.

The six modules, and the question each answers:

===================  =============================================================
Module               Question
===================  =============================================================
:mod:`percentiles`   How slow was the slow end? (nearest-rank p50/p95/p99)
:mod:`apdex`         How many users were unhappy? (satisfied/tolerating/frustrated)
:mod:`intervals`     How sure are we? (Wilson for rates, bootstrap for the rest)
:mod:`nonparametric` Is this release slower than that one? (Mann-Whitney U)
:mod:`changepoint`   Did it change, and stay changed? (EWMA vs CUSUM)
:mod:`baseline`      Is this unusual *for a Tuesday*? (hour-of-week, median + MAD)
===================  =============================================================
"""

from eventstore.perfmodel.apdex import ApdexScore, apdex
from eventstore.perfmodel.baseline import AnomalyScore, SeasonalBaseline, hour_of_week, scaled_mad
from eventstore.perfmodel.changepoint import DetectionResult, cusum_detect, ewma_detect
from eventstore.perfmodel.intervals import Interval, bootstrap_ci, wilson_interval
from eventstore.perfmodel.nonparametric import ComparisonResult, mann_whitney_u, rank_with_ties
from eventstore.perfmodel.percentiles import LatencySummary, percentile, summarize

__all__ = [
    "AnomalyScore",
    "ApdexScore",
    "ComparisonResult",
    "DetectionResult",
    "Interval",
    "LatencySummary",
    "SeasonalBaseline",
    "apdex",
    "bootstrap_ci",
    "cusum_detect",
    "ewma_detect",
    "hour_of_week",
    "mann_whitney_u",
    "percentile",
    "rank_with_ties",
    "scaled_mad",
    "summarize",
    "wilson_interval",
]
