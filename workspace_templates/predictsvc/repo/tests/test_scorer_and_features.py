"""Tests for the scorer and the feature pipeline.

Numeric expectations are hand-computed against the shipped artifact, with the
arithmetic in the docstring, so a failure means the model or the pipeline changed --
not that a snapshot drifted.
"""

import math

import pytest

from svc.features.pipeline import FeatureError, FeatureKind, build_features
from svc.model.registry import (
    ArtifactError,
    assert_compatible,
    load_feature_spec,
    load_model,
)
from svc.model.scorer import (
    MissingFeature,
    linear_predictor,
    predict,
    predict_proba,
    sigmoid,
)

pytestmark = pytest.mark.model


@pytest.fixture(scope="module")
def model():
    return load_model()


@pytest.fixture(scope="module")
def spec():
    return load_feature_spec()


# ---------------------------------------------------------------------------
# sigmoid
# ---------------------------------------------------------------------------


def test_sigmoid_at_zero_is_one_half():
    assert sigmoid(0.0) == 0.5


def test_sigmoid_is_symmetric():
    assert sigmoid(2.0) + sigmoid(-2.0) == pytest.approx(1.0)


@pytest.mark.parametrize("x", [800.0, -800.0, 1e6, -1e6])
def test_sigmoid_does_not_overflow_at_extremes(x):
    """The naive 1/(1+exp(-x)) form raises OverflowError for large negative x."""
    value = sigmoid(x)
    assert 0.0 <= value <= 1.0
    assert not math.isnan(value)


def test_sigmoid_is_monotonic():
    values = [sigmoid(x) for x in (-3, -1, 0, 1, 3)]
    assert values == sorted(values)


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------


def test_model_and_spec_are_compatible(model, spec):
    """The check that stops a model being served against the wrong feature contract."""
    assert_compatible(model, spec)


def test_model_declares_the_spec_it_was_trained_against(model, spec):
    assert model.feature_spec_version == spec.version


def test_every_model_coefficient_is_emitted_by_the_spec(model, spec):
    assert set(model.coefficients) <= set(spec.output_names)


def test_incompatible_versions_are_rejected(model, spec):
    stale = model.__class__(
        name=model.name,
        version=model.version,
        intercept=model.intercept,
        coefficients=model.coefficients,
        threshold=model.threshold,
        feature_spec_version="1.0",
    )
    with pytest.raises(ArtifactError, match="was trained against feature spec"):
        assert_compatible(stale, spec)


def test_a_spec_missing_a_required_feature_is_rejected(model, spec):
    trimmed = spec.__class__(
        version=spec.version, features=[f for f in spec.features if f.name != "seats"]
    )
    with pytest.raises(ArtifactError, match="does not emit features the model requires"):
        assert_compatible(model, trimmed)


# ---------------------------------------------------------------------------
# The feature pipeline
# ---------------------------------------------------------------------------


BASE_PAYLOAD = {
    "account_id": "acct-1",
    "plan": "team",
    "seats": 100,
    "monthly_spend": 1000,
    "tenure_days": 365,
    "support_tickets": 0,
    "has_sso": True,
}


def test_pipeline_emits_exactly_the_declared_names(spec):
    vector = build_features(spec, BASE_PAYLOAD)
    assert sorted(vector) == sorted(spec.output_names)


def test_pipeline_width_is_fixed_by_the_spec(spec):
    """Whatever arrives, the consumer gets the same number of features."""
    for plan in ("free", "team", "enterprise"):
        vector = build_features(spec, {**BASE_PAYLOAD, "plan": plan})
        assert len(vector) == len(spec.output_names)


def test_numeric_features_are_scaled_by_the_spec(spec):
    """seats=100 with scale 100 gives 1.0; spend=1000 with scale 1000 gives 1.0."""
    vector = build_features(spec, BASE_PAYLOAD)
    assert vector["seats"] == pytest.approx(1.0)
    assert vector["monthly_spend"] == pytest.approx(1.0)
    assert vector["tenure_days"] == pytest.approx(1.0)


def test_numeric_features_are_clipped(spec):
    """seats has clip_max 10, so 5000 seats (=50 scaled) clamps to 10."""
    vector = build_features(spec, {**BASE_PAYLOAD, "seats": 5000})
    assert vector["seats"] == pytest.approx(10.0)


def test_categorical_one_hot_is_exclusive(spec):
    vector = build_features(spec, {**BASE_PAYLOAD, "plan": "enterprise"})
    assert vector["plan__enterprise"] == 1.0
    assert vector["plan__free"] == 0.0
    assert vector["plan__team"] == 0.0


def test_an_unknown_category_is_rejected_not_defaulted(spec):
    """Quietly substituting a category produces a confident wrong prediction."""
    with pytest.raises(FeatureError, match="must be one of"):
        build_features(spec, {**BASE_PAYLOAD, "plan": "platinum"})


def test_a_missing_required_field_is_rejected(spec):
    payload = {k: v for k, v in BASE_PAYLOAD.items() if k != "seats"}
    with pytest.raises(FeatureError, match="is required"):
        build_features(spec, payload)


def test_an_optional_field_uses_its_declared_default(spec):
    payload = {k: v for k, v in BASE_PAYLOAD.items() if k != "support_tickets"}
    assert build_features(spec, payload)["support_tickets"] == 0.0


def test_a_null_optional_field_uses_the_default(spec):
    vector = build_features(spec, {**BASE_PAYLOAD, "tenure_days": None})
    assert vector["tenure_days"] == 0.0


def test_unparseable_numbers_are_rejected(spec):
    with pytest.raises(FeatureError, match="must be a number"):
        build_features(spec, {**BASE_PAYLOAD, "seats": "many"})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(True, 1.0), (False, 0.0), ("true", 1.0), ("no", 0.0), ("YES", 1.0), (1, 1.0), (0, 0.0)],
)
def test_boolean_spellings(spec, raw, expected):
    assert build_features(spec, {**BASE_PAYLOAD, "has_sso": raw})["has_sso"] == expected


def test_an_unparseable_boolean_is_rejected(spec):
    with pytest.raises(FeatureError, match="must be a boolean"):
        build_features(spec, {**BASE_PAYLOAD, "has_sso": "maybe"})


def test_spec_reports_its_required_sources(spec):
    assert "seats" in spec.required_sources
    assert "support_tickets" not in spec.required_sources


# ---------------------------------------------------------------------------
# Scoring, hand-computed
# ---------------------------------------------------------------------------


def test_linear_predictor_matches_hand_computation(model, spec):
    """Hand-computed against artifacts/model_v3.json.

    seats=1.0, monthly_spend=1.0, tenure_days=1.0, support_tickets=0.0,
    has_sso=1.0, plan=team.

      -1.2 (intercept)
      -0.8 (seats)      -0.5 (spend)   -1.1 (tenure)
      +0.0 (tickets)    -0.6 (sso)     +0.2 (plan__team)
      = -4.0
    """
    vector = build_features(spec, BASE_PAYLOAD)
    assert linear_predictor(model, vector) == pytest.approx(-4.0)


def test_probability_matches_hand_computation(model, spec):
    """sigmoid(-4.0) = 1/(1+e^4) = 0.01798620996..."""
    vector = build_features(spec, BASE_PAYLOAD)
    assert predict_proba(model, vector) == pytest.approx(0.0179862, abs=1e-6)


def test_a_free_plan_at_zero_everything_is_hand_computable(model, spec):
    """-1.2 + 1.5 (plan__free) = 0.3, and sigmoid(0.3) = 0.574442516..."""
    payload = {
        "account_id": "a",
        "plan": "free",
        "seats": 0,
        "monthly_spend": 0,
        "tenure_days": 0,
        "support_tickets": 0,
        "has_sso": False,
    }
    vector = build_features(spec, payload)
    assert linear_predictor(model, vector) == pytest.approx(0.3)
    assert predict_proba(model, vector) == pytest.approx(0.5744425, abs=1e-6)


def test_label_follows_the_threshold(model, spec):
    """The free-plan case is above 0.5, the team case well below."""
    free = build_features(spec, {**BASE_PAYLOAD, "plan": "free", "seats": 0, "monthly_spend": 0,
                                 "tenure_days": 0, "has_sso": False})
    assert predict(model, free)[0] == 1
    assert predict(model, build_features(spec, BASE_PAYLOAD))[0] == 0


def test_support_tickets_increase_risk(model, spec):
    """The coefficient is positive, so more tickets must not lower the probability."""
    low = predict_proba(model, build_features(spec, {**BASE_PAYLOAD, "support_tickets": 0}))
    high = predict_proba(model, build_features(spec, {**BASE_PAYLOAD, "support_tickets": 50}))
    assert high > low


def test_a_missing_feature_raises_rather_than_scoring_zero(model):
    """Treating an absent feature as zero is a silent, plausible wrong answer."""
    with pytest.raises(MissingFeature, match="is required by model"):
        linear_predictor(model, {"seats": 1.0})


def test_scoring_is_deterministic(model, spec):
    vector = build_features(spec, BASE_PAYLOAD)
    assert len({predict_proba(model, vector) for _ in range(50)}) == 1


def test_feature_order_does_not_affect_the_score(model, spec):
    """Lookup is by name, so a reordered pipeline cannot misalign the weights."""
    vector = build_features(spec, BASE_PAYLOAD)
    shuffled = dict(reversed(list(vector.items())))
    assert linear_predictor(model, shuffled) == pytest.approx(linear_predictor(model, vector))


def test_spec_declares_a_categorical_feature(spec):
    kinds = {feature.kind for feature in spec.features}
    assert FeatureKind.CATEGORICAL in kinds
