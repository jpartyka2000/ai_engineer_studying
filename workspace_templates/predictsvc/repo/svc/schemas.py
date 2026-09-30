"""Request and response schemas.

Validation is deliberately strict: unknown fields are rejected rather than ignored.
A caller who misspells ``monthly_spend`` should get a 422 telling them so, not a
silently-defaulted prediction that looks plausible and is wrong.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PredictRequest(BaseModel):
    """One account to score."""

    # forbid, not ignore: a typo'd field name must be an error, not a default.
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1, max_length=64)
    plan: Literal["free", "team", "enterprise"]
    seats: int = Field(ge=0, le=100_000)
    monthly_spend: float = Field(ge=0, le=10_000_000)
    tenure_days: int | None = Field(default=None, ge=0, le=20_000)
    support_tickets: int | None = Field(default=None, ge=0, le=10_000)
    has_sso: bool | None = None


class BatchPredictRequest(BaseModel):
    """Several accounts in one call."""

    model_config = ConfigDict(extra="forbid")

    # Bounded so one request cannot tie up a worker indefinitely.
    accounts: list[PredictRequest] = Field(min_length=1, max_length=500)


class Prediction(BaseModel):
    """The score for one account."""

    account_id: str
    label: int
    probability: float
    model_version: str
    feature_spec_version: str


class BatchPredictResponse(BaseModel):
    """Scores for a batch, plus a count of what could not be scored."""

    predictions: list[Prediction]
    scored: int
    rejected: int


class RejectedAccount(BaseModel):
    """An account the pipeline refused, and why."""

    account_id: str
    reason: str


class HealthResponse(BaseModel):
    """Liveness and readiness."""

    status: str
    model_version: str | None = None
    feature_spec_version: str | None = None
    detail: str | None = None
