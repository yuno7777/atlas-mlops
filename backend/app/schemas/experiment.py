from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ExperimentSummary(BaseModel):
    id: str
    project_id: str
    training_job_id: str
    dataset_version_id: str
    dataset_name: str | None = None
    dataset_version: int | None = None
    name: str
    algorithm: str
    algorithm_label: str
    problem_type: str
    params: dict[str, Any]
    metrics: dict[str, Any]
    cv_metrics: dict[str, Any] | None
    status: str
    error_message: str | None
    mlflow_run_id: str | None
    tracking_warning: str | None
    training_duration_seconds: float | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    registered_model_id: str | None = None
    registered_model_name: str | None = None
    registered_version: int | None = None
    registered_stage: str | None = None
    artifact_available: bool = False


class ExperimentDetail(ExperimentSummary):
    reference_profile: dict[str, Any] | None = None
    job_name: str | None = None


class ExperimentCompareRequest(BaseModel):
    experiment_ids: list[str] = Field(min_length=2, max_length=6)


class BestMetric(BaseModel):
    experiment_id: str
    value: float
    direction: str


class ExperimentCompareResponse(BaseModel):
    problem_type: str
    metric_keys: list[str]
    directions: dict[str, str]
    best: dict[str, BestMetric]
    experiments: list[ExperimentSummary]
