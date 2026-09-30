"""The feature pipeline.

Turns a raw scoring request into the numeric vector the model expects. Driven entirely
by ``artifacts/feature_spec.json``, so the transformation applied at serving time is
the one that was declared at training time -- and any divergence is a data change
rather than a code change.

This is the layer where train/serve skew lives. Every default, every category
encoding, every clipping bound is read from the spec rather than hardcoded here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class FeatureKind(StrEnum):
    """How a raw field becomes a number."""

    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    BOOLEAN = "boolean"


@dataclass(frozen=True)
class FeatureDef:
    """How to derive one model feature from a raw request.

    Attributes:
        name: The model feature name.
        source: The raw request field it comes from.
        kind: How to interpret the raw value.
        default: Value used when the field is absent or null. ``None`` means the field
            is required.
        categories: For categorical features, the accepted values in the order the
            model was trained on.
        clip_min: Lower clipping bound, applied after scaling.
        clip_max: Upper clipping bound.
        scale: Divisor applied to numeric values, so the served magnitude matches
            training.
    """

    name: str
    source: str
    kind: FeatureKind
    default: float | str | None = None
    categories: list[str] = field(default_factory=list)
    clip_min: float | None = None
    clip_max: float | None = None
    scale: float = 1.0

    @property
    def is_required(self) -> bool:
        """Whether a request must supply this field."""
        return self.default is None


@dataclass(frozen=True)
class FeatureSpec:
    """The full declared feature contract."""

    version: str
    features: list[FeatureDef]

    @property
    def required_sources(self) -> list[str]:
        """Raw fields a request must contain, sorted."""
        return sorted({f.source for f in self.features if f.is_required})

    @property
    def output_names(self) -> list[str]:
        """Every feature name the pipeline emits, in spec order.

        Categorical features expand to one name per category, so the width is fixed by
        the spec and cannot vary with the request.
        """
        names: list[str] = []
        for feature in self.features:
            if feature.kind == FeatureKind.CATEGORICAL:
                names.extend(f"{feature.name}__{category}" for category in feature.categories)
            else:
                names.append(feature.name)
        return names


class FeatureError(ValueError):
    """Raised when a request cannot be turned into a valid feature vector."""


def _coerce_number(raw: object, feature: FeatureDef) -> float:
    """Parse a raw value as a float, with a useful message on failure."""
    try:
        return float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise FeatureError(
            f"field {feature.source!r} must be a number, got {raw!r}"
        ) from exc


def _apply_bounds(value: float, feature: FeatureDef) -> float:
    """Scale and clip a numeric value per the spec."""
    scaled = value / feature.scale if feature.scale else value
    if feature.clip_min is not None:
        scaled = max(scaled, feature.clip_min)
    if feature.clip_max is not None:
        scaled = min(scaled, feature.clip_max)
    return scaled


def build_features(spec: FeatureSpec, payload: dict[str, object]) -> dict[str, float]:
    """Turn a raw request into the model's feature vector.

    Args:
        spec: The declared feature contract.
        payload: The raw request body.

    Returns:
        Feature name to numeric value, containing exactly
        :attr:`FeatureSpec.output_names`.

    Raises:
        FeatureError: If a required field is missing, a value cannot be coerced, or a
            categorical value is not in the declared set. All three fail loudly rather
            than defaulting, because a quietly-substituted value produces a confident
            wrong prediction.
    """
    vector: dict[str, float] = {}

    for feature in spec.features:
        present = feature.source in payload and payload[feature.source] is not None
        if not present and feature.is_required:
            raise FeatureError(f"field {feature.source!r} is required")

        raw = payload[feature.source] if present else feature.default

        if feature.kind == FeatureKind.NUMERIC:
            vector[feature.name] = _apply_bounds(_coerce_number(raw, feature), feature)

        elif feature.kind == FeatureKind.BOOLEAN:
            if isinstance(raw, bool):
                vector[feature.name] = 1.0 if raw else 0.0
            elif isinstance(raw, str):
                lowered = raw.strip().lower()
                if lowered not in {"true", "false", "1", "0", "yes", "no"}:
                    raise FeatureError(
                        f"field {feature.source!r} must be a boolean, got {raw!r}"
                    )
                vector[feature.name] = 1.0 if lowered in {"true", "1", "yes"} else 0.0
            else:
                vector[feature.name] = 1.0 if _coerce_number(raw, feature) else 0.0

        else:  # CATEGORICAL
            value = str(raw).strip() if raw is not None else ""
            if value not in feature.categories:
                raise FeatureError(
                    f"field {feature.source!r} must be one of {feature.categories}, "
                    f"got {value!r}"
                )
            # One-hot over the declared categories. Every column is emitted, so the
            # vector width is fixed by the spec rather than by which value arrived.
            for category in feature.categories:
                vector[f"{feature.name}__{category}"] = 1.0 if category == value else 0.0

    return vector
