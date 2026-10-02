"""Apdex, the one-number user-satisfaction score.

Apdex buckets every request against a target time ``T``:

===========  ==========================  ======
Bucket       Condition                   Weight
===========  ==========================  ======
satisfied    ``latency <= T``            1
tolerating   ``T < latency <= 4T``       0.5
frustrated   ``latency > 4T``            0
===========  ==========================  ======

and the score is ``(satisfied + tolerating/2) / total``, a number in ``[0, 1]``.

**The half-weight is the whole point of the metric.** A tolerating request is a request
the user noticed, and counting it as a success is how a service with a visibly degraded
tail reports a near-perfect score. The 4T frustration boundary is from the Apdex
specification, not a local choice, which is what makes scores comparable between teams.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

#: Apdex's frustration boundary is four times the target. Named rather than inlined so
#: that a reader can see it is a constant from the specification and not a tunable.
FRUSTRATION_MULTIPLIER = 4


@dataclass(frozen=True)
class ApdexScore:
    """An Apdex score together with the bucket counts it was computed from.

    The counts travel with the score because a bare 0.84 is unactionable: the same
    score comes from "many tolerating" and from "a few frustrated", and the fixes
    are different.

    Attributes:
        target_ms: The target time ``T`` in milliseconds.
        satisfied: Requests at or under ``T``.
        tolerating: Requests over ``T`` and at or under ``4T``.
        frustrated: Requests over ``4T``.
        score: ``(satisfied + tolerating/2) / total``, or 1.0 for no requests.
    """

    target_ms: float
    satisfied: int
    tolerating: int
    frustrated: int
    score: float

    @property
    def total(self) -> int:
        """Total requests scored."""
        return self.satisfied + self.tolerating + self.frustrated

    def as_dict(self) -> dict[str, float | int]:
        """Return the score as a JSON-serialisable dict."""
        return {
            "target_ms": self.target_ms,
            "satisfied": self.satisfied,
            "tolerating": self.tolerating,
            "frustrated": self.frustrated,
            "total": self.total,
            "score": self.score,
        }


def apdex(latencies: Iterable[float], target_ms: float) -> ApdexScore:
    """Score a latency sample against a target time.

    Args:
        latencies: Observed latencies in milliseconds.
        target_ms: The Apdex target ``T``, strictly positive.

    Returns:
        An :class:`ApdexScore`. An empty sample scores 1.0 with all buckets at zero:
        no request was dissatisfied because no request was made. The caller can tell
        this case from a real 1.0 by looking at ``total``.

    Raises:
        ValueError: If ``target_ms`` is not strictly positive.

    Example:
        With ``T = 100`` and latencies ``[50, 120, 500]`` the buckets are one
        satisfied, one tolerating (120 <= 400) and one frustrated (500 > 400), so the
        score is ``(1 + 0.5) / 3 = 0.5``.
    """
    if target_ms <= 0:
        raise ValueError(f"target_ms must be > 0, got {target_ms!r}")

    frustration_boundary = FRUSTRATION_MULTIPLIER * target_ms
    satisfied = tolerating = frustrated = 0
    for latency in latencies:
        if latency <= target_ms:
            satisfied += 1
        elif latency <= frustration_boundary:
            tolerating += 1
        else:
            frustrated += 1

    total = satisfied + tolerating + frustrated
    score = 1.0 if total == 0 else (satisfied + tolerating / 2) / total
    return ApdexScore(
        target_ms=float(target_ms),
        satisfied=satisfied,
        tolerating=tolerating,
        frustrated=frustrated,
        score=score,
    )
