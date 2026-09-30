"""Classification metrics.

Hand-written rather than imported, so every number is checkable against a confusion
matrix you can count on paper.

**Accuracy is deliberately not the headline metric here.** The evaluation set is about
9.5% positive, so a model that always predicts "no churn" scores over 90% accuracy
while being entirely useless. F1 is reported as the primary figure for that reason, and
the majority-class baseline is reported alongside it so the comparison is unavoidable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfusionMatrix:
    """Counts of the four outcomes."""

    true_positive: int = 0
    false_positive: int = 0
    true_negative: int = 0
    false_negative: int = 0

    @property
    def total(self) -> int:
        """Number of predictions."""
        return (
            self.true_positive + self.false_positive + self.true_negative + self.false_negative
        )

    @property
    def accuracy(self) -> float:
        """Proportion correct. Misleading on imbalanced data -- see the module docstring."""
        if self.total == 0:
            return 0.0
        return (self.true_positive + self.true_negative) / self.total

    @property
    def precision(self) -> float:
        """Of those predicted positive, how many were. 0.0 when none were predicted."""
        predicted = self.true_positive + self.false_positive
        if predicted == 0:
            return 0.0
        return self.true_positive / predicted

    @property
    def recall(self) -> float:
        """Of the actual positives, how many were caught. 0.0 when there are none."""
        actual = self.true_positive + self.false_negative
        if actual == 0:
            return 0.0
        return self.true_positive / actual

    @property
    def f1(self) -> float:
        """Harmonic mean of precision and recall.

        Returns 0.0 when either is zero, which is the correct reading: a model that
        never predicts the positive class has not solved the problem, whatever its
        accuracy says.
        """
        if self.precision + self.recall == 0:
            return 0.0
        return 2 * self.precision * self.recall / (self.precision + self.recall)

    @property
    def positive_rate(self) -> float:
        """Proportion of the set that is actually positive."""
        if self.total == 0:
            return 0.0
        return (self.true_positive + self.false_negative) / self.total

    @property
    def majority_baseline_accuracy(self) -> float:
        """Accuracy of always predicting the majority class.

        Reported next to accuracy so an impressive-looking score cannot be mistaken
        for an impressive model.
        """
        rate = self.positive_rate
        return max(rate, 1 - rate)

    def as_dict(self) -> dict[str, float | int]:
        """Return every figure, for JSON output."""
        return {
            "total": self.total,
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "true_negative": self.true_negative,
            "false_negative": self.false_negative,
            "accuracy": round(self.accuracy, 6),
            "precision": round(self.precision, 6),
            "recall": round(self.recall, 6),
            "f1": round(self.f1, 6),
            "positive_rate": round(self.positive_rate, 6),
            "majority_baseline_accuracy": round(self.majority_baseline_accuracy, 6),
        }


def confusion_matrix(actual: list[int], predicted: list[int]) -> ConfusionMatrix:
    """Build a confusion matrix from two label sequences.

    Args:
        actual: Ground-truth labels, 0 or 1.
        predicted: Predicted labels, 0 or 1.

    Returns:
        The :class:`ConfusionMatrix`.

    Raises:
        ValueError: If the sequences differ in length, or contain a value that is not
            0 or 1 -- which usually means probabilities were passed by mistake.
    """
    if len(actual) != len(predicted):
        raise ValueError(f"length mismatch: {len(actual)} actual, {len(predicted)} predicted")

    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    for truth, guess in zip(actual, predicted, strict=True):
        if truth not in (0, 1) or guess not in (0, 1):
            raise ValueError(f"labels must be 0 or 1, got actual={truth!r} predicted={guess!r}")
        if truth == 1 and guess == 1:
            counts["tp"] += 1
        elif truth == 0 and guess == 1:
            counts["fp"] += 1
        elif truth == 0 and guess == 0:
            counts["tn"] += 1
        else:
            counts["fn"] += 1

    return ConfusionMatrix(
        true_positive=counts["tp"],
        false_positive=counts["fp"],
        true_negative=counts["tn"],
        false_negative=counts["fn"],
    )
