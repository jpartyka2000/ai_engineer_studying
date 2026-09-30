"""Model scoring.

A hand-written logistic-regression scorer over a coefficient artifact, rather than a
pickled estimator from a library. Three reasons this is the right shape here:

* **Reproducible.** A dot product and a sigmoid give the same answer on every
  platform and every Python version. An unpickled estimator does not.
* **Inspectable.** The coefficients are JSON. You can read them, diff them in a pull
  request, and hand-compute an expected score.
* **No unpickling.** Loading a pickle executes whatever is inside it, so a model
  registry becomes a code-execution path.

The trade-off is that training happens elsewhere; this service only serves.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelArtifact:
    """A trained linear model, loaded from JSON.

    Attributes:
        name: Model name.
        version: Semantic version of the artifact.
        intercept: The bias term.
        coefficients: Feature name to weight. Feature order is irrelevant because
            lookup is by name -- which is what stops a reordered feature pipeline
            silently scoring against the wrong weights.
        threshold: Probability at or above which the prediction is the positive class.
        feature_spec_version: The feature-spec version this model was trained against.
    """

    name: str
    version: str
    intercept: float
    coefficients: dict[str, float]
    threshold: float = 0.5
    feature_spec_version: str = ""

    @property
    def feature_names(self) -> list[str]:
        """The features this model expects, sorted for stable reporting."""
        return sorted(self.coefficients)


def sigmoid(x: float) -> float:
    """Return the logistic function of ``x``.

    Split into two branches to avoid overflow: ``math.exp`` of a large positive number
    raises ``OverflowError``, and the naive ``1/(1+exp(-x))`` form hits that for
    strongly negative inputs.

    Args:
        x: The linear predictor.

    Returns:
        A probability in (0, 1).
    """
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exponent = math.exp(x)
    return exponent / (1.0 + exponent)


class MissingFeature(KeyError):
    """Raised when a required feature is absent from a scoring request."""


def linear_predictor(model: ModelArtifact, features: dict[str, float]) -> float:
    """Compute the linear predictor for one feature vector.

    Args:
        model: The loaded artifact.
        features: Feature name to value.

    Returns:
        ``intercept + sum(weight * value)``.

    Raises:
        MissingFeature: If a coefficient has no corresponding feature. Failing loudly
            matters: treating an absent feature as zero is a silent, plausible-looking
            wrong answer, and zero is a meaningful value for most of these features.
    """
    total = model.intercept
    for name, weight in model.coefficients.items():
        if name not in features:
            raise MissingFeature(
                f"feature {name!r} is required by model {model.name} v{model.version}"
            )
        total += weight * features[name]
    return total


def predict_proba(model: ModelArtifact, features: dict[str, float]) -> float:
    """Return the probability of the positive class."""
    return sigmoid(linear_predictor(model, features))


def predict(model: ModelArtifact, features: dict[str, float]) -> tuple[int, float]:
    """Return ``(label, probability)`` for one feature vector.

    Args:
        model: The loaded artifact.
        features: Feature name to value.

    Returns:
        The label is 1 when the probability is at or above the model's threshold.
        Comparison is ``>=`` so a threshold of 0.0 predicts the positive class for
        everything, which is what a caller asking for that would expect.
    """
    probability = predict_proba(model, features)
    return (1 if probability >= model.threshold else 0), probability
