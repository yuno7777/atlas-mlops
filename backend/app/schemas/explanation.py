from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ExplanationRequest(BaseModel):
    record: dict[str, Any]


class FeatureContribution(BaseModel):
    feature: str
    value: Any
    contribution: float
    direction: str


class ExplanationResponse(BaseModel):
    deployment_id: str
    model_version_id: str
    model_version: int
    problem_type: str
    method: str
    baseline: float
    prediction: float
    contributions: list[FeatureContribution]
    background_samples: int
    permutations: int
    latency_ms: float
