"""Liveness and readiness endpoints.

Kept distinct on purpose. ``/healthz`` says the process is up; ``/readyz`` says it can
actually serve, which means the artifacts loaded and validated. A deployment that
conflates them will happily route traffic to a container whose model failed to load.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status

from svc.model.registry import ArtifactError, get_loaded_model
from svc.schemas import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    """Liveness. Deliberately does not touch the model."""
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=HealthResponse)
def readyz(response: Response) -> HealthResponse:
    """Readiness: whether this instance can serve a prediction right now.

    Returns 503 with the reason when the artifacts are unusable, so the failure shows
    up in a load balancer rather than as wrong predictions.
    """
    try:
        loaded = get_loaded_model()
    except ArtifactError as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="unavailable", detail=str(exc))

    return HealthResponse(
        status="ready",
        model_version=loaded.model.version,
        feature_spec_version=loaded.spec.version,
    )
