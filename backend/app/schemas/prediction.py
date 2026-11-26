from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StrictBool, StrictInt, StrictStr

TabularValue = StrictStr | StrictBool | StrictInt | FiniteFloat | None


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    records: list[dict[str, TabularValue]] = Field(min_length=1, max_length=1000)


class PredictionItem(BaseModel):
    prediction: TabularValue
    probabilities: dict[str, FiniteFloat] | None = None


class PredictionResponse(BaseModel):
    request_id: str
    deployment_id: str
    model_version_id: str
    model_version: int
    variant: str = "champion"
    predictions: list[PredictionItem]
    latency_ms: FiniteFloat
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
