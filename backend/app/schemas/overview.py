from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class OverviewCounts(BaseModel):
    datasets: int
    dataset_versions: int
    experiments: int
    completed_experiments: int
    registered_models: int
    model_versions: int
    active_deployments: int
    training_jobs: int
    predictions_7d: int


class TrainingActivityPoint(BaseModel):
    date: date
    completed: int
    failed: int
    running: int
    total: int


class PerformancePoint(BaseModel):
    date: datetime
    experiment_id: str
    name: str
    algorithm: str
    primary_metric: str
    value: float
    problem_type: str


class ModelPerformanceItem(BaseModel):
    algorithm: str
    algorithm_label: str
    runs: int
    primary_metric: str
    average: float
    best: float


class DeploymentHealthItem(BaseModel):
    id: str
    name: str
    status: str
    model_name: str
    model_version: int
    latest_monitoring_status: str | None
    last_request_at: datetime | None
    created_at: datetime


class RecentJobItem(BaseModel):
    id: str
    name: str
    status: str
    progress: int
    problem_type: str
    created_at: datetime


class RecentEventItem(BaseModel):
    id: int
    action: str
    resource_type: str
    resource_id: str | None
    details: dict[str, Any]
    created_at: datetime


class LatestModelItem(BaseModel):
    id: str
    name: str
    version: int
    stage: str
    algorithm: str
    metrics: dict[str, Any]
    created_at: datetime


class OverviewResponse(BaseModel):
    counts: OverviewCounts
    training_activity: list[TrainingActivityPoint]
    experiment_performance: list[PerformancePoint]
    model_performance: list[ModelPerformanceItem]
    deployment_health: list[DeploymentHealthItem]
    deployment_status_counts: dict[str, int]
    recent_jobs: list[RecentJobItem]
    recent_events: list[RecentEventItem]
    latest_models: list[LatestModelItem]
    primary_metric: str | None
