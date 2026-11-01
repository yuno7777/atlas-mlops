from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.experiment import ExperimentSummary


class MonitoringResultOut(BaseModel):
    id: str
    deployment_id: str
    model_version_id: str
    status: str
    sample_count: int
    labeled_count: int
    data_drift_detected: bool
    prediction_drift_detected: bool
    concept_drift_detected: bool
    drift_share: float
    psi_max: float
    ks_min_pvalue: float | None
    details: dict[str, Any]
    created_at: datetime


class TimeseriesPoint(BaseModel):
    bucket: datetime
    predictions: int
    failures: int
    avg_latency_ms: float
    p95_latency_ms: float


class TimeseriesResponse(BaseModel):
    deployment_id: str
    hours: int
    points: list[TimeseriesPoint]


class RetrainRequest(BaseModel):
    dataset_version_id: str | None = None
    name: str | None = None


class IncumbentInfo(BaseModel):
    model_version_id: str
    version: int
    algorithm: str
    metrics: dict[str, Any]


class RetrainComparisonResponse(BaseModel):
    deployment_id: str
    incumbent: IncumbentInfo
    candidates: list[ExperimentSummary]
    metric_keys: list[str]
    directions: dict[str, str]
    deltas: dict[str, dict[str, float]]
    recommended_experiment_id: str | None
    recommendation_reason: str
    latest_job_id: str | None
    latest_job_status: str | None
