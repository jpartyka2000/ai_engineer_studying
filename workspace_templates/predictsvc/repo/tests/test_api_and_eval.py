"""API contract tests and evaluation-metric tests.

The contract tests care as much about the rejection cases as the happy path: a scoring
service that accepts a misspelled field and returns a plausible number is worse than
one that refuses.
"""

import pytest
from fastapi.testclient import TestClient

from eval.metrics import ConfusionMatrix, confusion_matrix
from eval.run_eval import DEFAULT_DATASET, evaluate, load_rows
from svc.main import create_app

VALID = {
    "account_id": "acct-1",
    "plan": "team",
    "seats": 100,
    "monthly_spend": 1000,
    "tenure_days": 365,
    "support_tickets": 0,
    "has_sso": True,
}


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@pytest.mark.contract
def test_healthz_does_not_touch_the_model(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.contract
def test_readyz_reports_the_loaded_versions(client):
    """Distinct from healthz: readiness means it can actually serve."""
    body = client.get("/readyz").json()
    assert body["status"] == "ready"
    assert body["model_version"]
    assert body["feature_spec_version"]


# ---------------------------------------------------------------------------
# Single prediction
# ---------------------------------------------------------------------------


@pytest.mark.contract
def test_readyz_reports_503_when_the_artifacts_cannot_load(tmp_path, monkeypatch):
    """Readiness has to fail when this instance cannot actually serve.

    The compose healthcheck hits /readyz for exactly this reason: a container whose
    model failed to load must never be routed traffic. The happy-path test above would
    pass just as well if /readyz never touched the model at all, so this is the case
    that distinguishes a readiness probe from a liveness one.

    /healthz must stay 200 throughout -- the process is alive, it just cannot serve.
    """
    from svc.model import registry

    monkeypatch.setattr(registry, "ARTIFACT_DIR", tmp_path)
    registry.reset_cache()
    try:
        probe = TestClient(create_app())
        ready = probe.get("/readyz")
        alive = probe.get("/healthz")
    finally:
        registry.reset_cache()

    assert ready.status_code == 503
    assert ready.json()["status"] == "unavailable"
    assert ready.json()["detail"], "a 503 must say what is wrong"
    assert alive.status_code == 200


@pytest.mark.contract
def test_predict_returns_a_label_and_probability(client):
    body = client.post("/predict", json=VALID).json()
    assert body["label"] in (0, 1)
    assert 0.0 <= body["probability"] <= 1.0
    assert body["account_id"] == "acct-1"


@pytest.mark.contract
def test_predict_reports_which_model_scored_it(client):
    """Without this a stored prediction cannot be traced to the model that made it."""
    body = client.post("/predict", json=VALID).json()
    assert body["model_version"]
    assert body["feature_spec_version"]


@pytest.mark.contract
def test_predict_matches_the_hand_computed_probability(client):
    """sigmoid(-4.0), the same figure the scorer tests derive."""
    assert client.post("/predict", json=VALID).json()["probability"] == pytest.approx(
        0.017986, abs=1e-5
    )


@pytest.mark.contract
def test_a_misspelled_field_is_rejected_not_ignored(client):
    """The failure this service exists to avoid: a typo yielding a confident number."""
    payload = {**VALID}
    payload["monthy_spend"] = payload.pop("monthly_spend")
    assert client.post("/predict", json=payload).status_code == 422


@pytest.mark.contract
@pytest.mark.parametrize(
    "mutation",
    [
        {"plan": "platinum"},
        {"seats": -1},
        {"monthly_spend": -10},
        {"tenure_days": -5},
        {"support_tickets": -1},
        {"account_id": ""},
        {"seats": "many"},
    ],
)
def test_invalid_values_are_rejected(client, mutation):
    assert client.post("/predict", json={**VALID, **mutation}).status_code == 422


@pytest.mark.contract
def test_a_missing_required_field_is_rejected(client):
    payload = {k: v for k, v in VALID.items() if k != "plan"}
    assert client.post("/predict", json=payload).status_code == 422


@pytest.mark.contract
def test_optional_fields_may_be_omitted(client):
    payload = {k: v for k, v in VALID.items() if k not in {"tenure_days", "support_tickets", "has_sso"}}
    assert client.post("/predict", json=payload).status_code == 200


@pytest.mark.contract
def test_a_get_on_predict_is_rejected(client):
    assert client.get("/predict").status_code == 405


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------


@pytest.mark.contract
def test_batch_scores_every_account(client):
    body = client.post("/predict/batch", json={"accounts": [VALID, {**VALID, "account_id": "b"}]}).json()
    assert body["scored"] == 2
    assert body["rejected"] == 0
    assert len(body["predictions"]) == 2


@pytest.mark.contract
def test_an_empty_batch_is_rejected(client):
    assert client.post("/predict/batch", json={"accounts": []}).status_code == 422


@pytest.mark.contract
def test_an_oversized_batch_is_rejected(client):
    """Bounded so one request cannot tie up a worker indefinitely."""
    accounts = [{**VALID, "account_id": f"a{i}"} for i in range(501)]
    assert client.post("/predict/batch", json={"accounts": accounts}).status_code == 422


@pytest.mark.contract
def test_batch_predictions_agree_with_single_predictions(client):
    single = client.post("/predict", json=VALID).json()
    batch = client.post("/predict/batch", json={"accounts": [VALID]}).json()
    assert batch["predictions"][0]["probability"] == single["probability"]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@pytest.mark.model
def test_confusion_matrix_counts_all_four_outcomes():
    matrix = confusion_matrix([1, 1, 0, 0], [1, 0, 1, 0])
    assert (matrix.true_positive, matrix.false_negative) == (1, 1)
    assert (matrix.false_positive, matrix.true_negative) == (1, 1)


@pytest.mark.model
def test_metrics_are_hand_computable():
    """tp=3 fp=1 tn=5 fn=1: precision 0.75, recall 0.75, F1 0.75, accuracy 0.8."""
    matrix = ConfusionMatrix(true_positive=3, false_positive=1, true_negative=5, false_negative=1)
    assert matrix.precision == pytest.approx(0.75)
    assert matrix.recall == pytest.approx(0.75)
    assert matrix.f1 == pytest.approx(0.75)
    assert matrix.accuracy == pytest.approx(0.8)


@pytest.mark.model
def test_f1_is_zero_when_nothing_positive_is_predicted():
    """The reading that matters: high accuracy, useless model."""
    matrix = ConfusionMatrix(true_positive=0, false_positive=0, true_negative=95, false_negative=5)
    assert matrix.accuracy == pytest.approx(0.95)
    assert matrix.f1 == 0.0


@pytest.mark.model
def test_majority_baseline_is_reported_next_to_accuracy():
    """So an impressive-looking accuracy cannot be mistaken for an impressive model."""
    matrix = ConfusionMatrix(true_positive=0, false_positive=0, true_negative=95, false_negative=5)
    assert matrix.majority_baseline_accuracy == pytest.approx(0.95)


@pytest.mark.model
def test_precision_and_recall_are_not_interchangeable():
    """tp=4 fp=6 tn=80 fn=1: precision 0.4, recall 0.8.

    Deliberately fp != fn. The fixture in ``test_metrics_are_hand_computable`` has
    fp == fn, which makes precision equal recall there -- so it would pass unchanged if
    the two were swapped, or if one were computed with the other's denominator. This is
    the case that can tell them apart.
    """
    matrix = ConfusionMatrix(true_positive=4, false_positive=6, true_negative=80, false_negative=1)
    assert matrix.precision == pytest.approx(0.4)
    assert matrix.recall == pytest.approx(0.8)


@pytest.mark.model
def test_f1_is_the_harmonic_mean_not_the_average():
    """tp=1 fp=0 tn=98 fn=9: precision 1.0, recall 0.1.

    F1 is 2pr/(p+r) = 0.1818, while the arithmetic mean of the same two numbers is
    0.55 -- a model that catches one churner in ten being reported as half-decent.

    Pinned on a case where precision and recall diverge sharply, because when they are
    close the two formulas agree to four decimal places: on the shipped model they
    differ by 0.0002, so neither the F1 gate nor any other test here would notice the
    wrong one. The harmonic mean punishes imbalance between the two, which is the
    entire reason it is the metric and not the average.
    """
    matrix = ConfusionMatrix(true_positive=1, false_positive=0, true_negative=98, false_negative=9)
    assert matrix.precision == pytest.approx(1.0)
    assert matrix.recall == pytest.approx(0.1)
    assert matrix.f1 == pytest.approx(0.181818, abs=1e-6)
    assert matrix.f1 < (matrix.precision + matrix.recall) / 2


@pytest.mark.model
def test_the_majority_baseline_holds_when_the_positive_class_is_the_majority():
    """tp=70 fn=0 tn=30 fp=0: 70% positive, so always-predict-positive scores 0.70.

    The baseline is the larger of the two class rates, not the negative rate. On this
    project's evaluation set the negatives are the majority, so the two definitions
    coincide and a wrong one would look right forever.
    """
    matrix = ConfusionMatrix(true_positive=70, false_positive=0, true_negative=30, false_negative=0)
    assert matrix.positive_rate == pytest.approx(0.7)
    assert matrix.majority_baseline_accuracy == pytest.approx(0.7)


@pytest.mark.model
def test_metrics_of_an_empty_matrix_are_zero_not_a_crash():
    matrix = ConfusionMatrix()
    assert (matrix.accuracy, matrix.precision, matrix.recall, matrix.f1) == (0.0, 0.0, 0.0, 0.0)


@pytest.mark.model
def test_confusion_matrix_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="length mismatch"):
        confusion_matrix([1, 0], [1])


@pytest.mark.model
def test_confusion_matrix_rejects_probabilities_passed_as_labels():
    """A common mistake: passing predict_proba output straight in."""
    with pytest.raises(ValueError, match="labels must be 0 or 1"):
        confusion_matrix([1, 0], [0.87, 0.12])


# ---------------------------------------------------------------------------
# End-to-end evaluation
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def evaluation():
    """Run the real evaluation once for the whole module."""
    return evaluate(load_rows(DEFAULT_DATASET))


@pytest.mark.model
def test_the_shipped_model_clears_the_f1_bar(evaluation):
    """The bar CI enforces, set just below the measured 0.8806 so a real regression
    fails while a candidate has room to change things.
    """
    assert evaluation["f1"] >= 0.80


@pytest.mark.model
def test_the_model_beats_the_majority_baseline(evaluation):
    assert evaluation["accuracy"] > evaluation["majority_baseline_accuracy"]


@pytest.mark.model
def test_every_row_in_the_evaluation_set_can_be_scored(evaluation):
    """A skipped row is a row the model got no credit for -- there should be none."""
    assert evaluation["skipped"] == 0
    assert evaluation["scored"] == evaluation["rows"]


@pytest.mark.model
def test_the_evaluation_set_is_imbalanced_as_documented(evaluation):
    """Pinned because it is why F1 leads rather than accuracy."""
    assert 0.05 < evaluation["positive_rate"] < 0.20
