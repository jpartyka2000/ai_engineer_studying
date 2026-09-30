"""Prediction endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from svc.features.pipeline import FeatureError, build_features
from svc.model.registry import ArtifactError, get_loaded_model
from svc.model.scorer import MissingFeature, predict
from svc.schemas import (
    BatchPredictRequest,
    BatchPredictResponse,
    Prediction,
    PredictRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["predict"])


def _score_one(loaded, request: PredictRequest) -> Prediction:
    """Score a single validated request.

    Raises:
        FeatureError: If the payload cannot become a valid feature vector.
        MissingFeature: If the pipeline output is missing something the model needs.
    """
    features = build_features(loaded.spec, request.model_dump())
    label, probability = predict(loaded.model, features)
    return Prediction(
        account_id=request.account_id,
        label=label,
        probability=round(probability, 6),
        model_version=loaded.model.version,
        feature_spec_version=loaded.spec.version,
    )


@router.post("/predict", response_model=Prediction)
def predict_one(request: PredictRequest) -> Prediction:
    """Score a single account.

    Raises:
        HTTPException: 422 when the payload cannot be turned into features, 503 when
            the model artifacts are unusable. The distinction matters: 422 is the
            caller's problem and 503 is ours.
    """
    try:
        loaded = get_loaded_model()
    except ArtifactError as exc:
        logger.error("cannot serve predictions: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    try:
        return _score_one(loaded, request)
    except (FeatureError, MissingFeature) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post("/predict/batch", response_model=BatchPredictResponse)
def predict_batch(request: BatchPredictRequest) -> BatchPredictResponse:
    """Score several accounts.

    A single unscoreable account does **not** fail the batch. It is counted in
    ``rejected`` and omitted from ``predictions``, so one bad row in a nightly job of
    500 does not discard the other 499. The count is reported rather than hidden, so a
    caller can tell the difference between "all scored" and "most scored".
    """
    try:
        loaded = get_loaded_model()
    except ArtifactError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    predictions: list[Prediction] = []
    rejected = 0
    for account in request.accounts:
        try:
            predictions.append(_score_one(loaded, account))
        except (FeatureError, MissingFeature) as exc:
            rejected += 1
            logger.info("rejected account %s: %s", account.account_id, exc)

    return BatchPredictResponse(
        predictions=predictions, scored=len(predictions), rejected=rejected
    )
