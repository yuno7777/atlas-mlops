from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PredictionRequest(BaseModel):
    records: list[dict[str, Any]] = Field(min_length=1, max_length=1000)


class PredictionItem(BaseModel):
    prediction: Any
    probabilities: dict[str, float] | None = None


class PredictionResponse(BaseModel):
    request_id: str
    deployment_id: str
    model_version_id: str
    model_version: int
    predictions: list[PredictionItem]
    latency_ms: float
    warnings: list[str] = Field(default_factory=list)


class FeedbackItem(BaseModel):
    prediction_id: str
    actual: Any


class FeedbackRequest(BaseModel):
    items: list[FeedbackItem] = Field(min_length=1, max_length=500)


class FeedbackResponse(BaseModel):
    updated: int
    already_labeled: int
    not_found: int
