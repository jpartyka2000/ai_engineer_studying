"""Loading model and feature-spec artifacts from disk.

Artifacts are JSON, loaded once at process start and cached. The registry refuses to
serve a model whose ``feature_spec_version`` does not match the loaded spec: a model
trained against one feature contract and served against another produces confident
nonsense, and that is the single easiest way to break this service invisibly.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from svc.features.pipeline import FeatureDef, FeatureKind, FeatureSpec
from svc.model.scorer import ModelArtifact

logger = logging.getLogger(__name__)

ARTIFACT_DIR = Path(os.environ.get("ARTIFACT_DIR", "artifacts"))
MODEL_FILENAME = "model_v3.json"
SPEC_FILENAME = "feature_spec.json"


class ArtifactError(RuntimeError):
    """Raised when an artifact is missing, malformed, or mismatched."""


@dataclass(frozen=True)
class LoadedModel:
    """A model paired with the feature spec it was trained against."""

    model: ModelArtifact
    spec: FeatureSpec

    @property
    def identifier(self) -> str:
        """Human-readable model identity, for logs and responses."""
        return f"{self.model.name}:{self.model.version}"


def _read_json(path: Path) -> dict:
    """Read a JSON artifact, raising :class:`ArtifactError` on any problem."""
    if not path.is_file():
        raise ArtifactError(f"artifact not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ArtifactError(f"{path} is not valid JSON: {exc}") from exc


def load_feature_spec(directory: Path | None = None) -> FeatureSpec:
    """Load the feature spec.

    Args:
        directory: Artifact directory; defaults to ``ARTIFACT_DIR``.

    Returns:
        The parsed :class:`~svc.features.pipeline.FeatureSpec`.

    Raises:
        ArtifactError: If the file is missing, malformed, or declares a feature with an
            unknown kind.
    """
    payload = _read_json((directory or ARTIFACT_DIR) / SPEC_FILENAME)
    features: list[FeatureDef] = []
    for entry in payload.get("features", []):
        try:
            kind = FeatureKind(entry["kind"])
        except (KeyError, ValueError) as exc:
            raise ArtifactError(f"bad feature kind in spec: {entry}") from exc
        features.append(
            FeatureDef(
                name=entry["name"],
                source=entry["source"],
                kind=kind,
                default=entry.get("default"),
                categories=list(entry.get("categories", [])),
                clip_min=entry.get("clip_min"),
                clip_max=entry.get("clip_max"),
                scale=float(entry.get("scale", 1.0)),
            )
        )
    if not features:
        raise ArtifactError("feature spec declares no features")
    return FeatureSpec(version=str(payload.get("version", "")), features=features)


def load_model(directory: Path | None = None) -> ModelArtifact:
    """Load the model artifact.

    Args:
        directory: Artifact directory; defaults to ``ARTIFACT_DIR``.

    Returns:
        The parsed :class:`~svc.model.scorer.ModelArtifact`.

    Raises:
        ArtifactError: If the file is missing, malformed, or has no coefficients.
    """
    payload = _read_json((directory or ARTIFACT_DIR) / MODEL_FILENAME)
    coefficients = payload.get("coefficients") or {}
    if not coefficients:
        raise ArtifactError("model artifact has no coefficients")
    return ModelArtifact(
        name=str(payload.get("name", "unnamed")),
        version=str(payload.get("version", "0")),
        intercept=float(payload.get("intercept", 0.0)),
        coefficients={name: float(weight) for name, weight in coefficients.items()},
        threshold=float(payload.get("threshold", 0.5)),
        feature_spec_version=str(payload.get("feature_spec_version", "")),
    )


def assert_compatible(model: ModelArtifact, spec: FeatureSpec) -> None:
    """Verify a model and a feature spec agree.

    Two independent checks, because they catch different mistakes. The version check
    catches "somebody shipped a new spec without retraining"; the name check catches
    "the spec emits a feature the model has never seen", which can happen even when
    the versions match because a spec edit forgot to bump.

    Args:
        model: The loaded model.
        spec: The loaded feature spec.

    Raises:
        ArtifactError: If the versions disagree, or the emitted feature names do not
            cover what the model requires.
    """
    if model.feature_spec_version and model.feature_spec_version != spec.version:
        raise ArtifactError(
            f"model {model.name} v{model.version} was trained against feature spec "
            f"{model.feature_spec_version!r} but spec {spec.version!r} is loaded"
        )

    emitted = set(spec.output_names)
    required = set(model.coefficients)
    missing = required - emitted
    if missing:
        raise ArtifactError(
            f"feature spec does not emit features the model requires: {sorted(missing)}"
        )

    unused = emitted - required
    if unused:
        # Not fatal: a spec may compute a feature this model ignores. Worth a log line
        # so nobody wonders why a new feature has no effect.
        logger.info("feature spec emits features model %s ignores: %s", model.name, sorted(unused))


@lru_cache(maxsize=1)
def get_loaded_model() -> LoadedModel:
    """Load and validate the model and spec once per process.

    Returns:
        The cached :class:`LoadedModel`.

    Raises:
        ArtifactError: If loading or compatibility checking fails. Raised at first use
            rather than swallowed, so a misconfigured deployment fails its healthcheck
            instead of serving wrong numbers.
    """
    model = load_model()
    spec = load_feature_spec()
    assert_compatible(model, spec)
    logger.info("loaded model %s:%s against spec %s", model.name, model.version, spec.version)
    return LoadedModel(model=model, spec=spec)


def reset_cache() -> None:
    """Clear the cached artifacts. For tests that swap artifact directories."""
    get_loaded_model.cache_clear()
