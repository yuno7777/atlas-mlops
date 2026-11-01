from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MonitoringConfig(BaseModel):
    psi_threshold: float = Field(default=0.2, gt=0, le=5)
    drift_share_threshold: float = Field(default=0.3, gt=0, le=1)
    performance_degradation_threshold: float = Field(default=0.15, gt=0, le=1)
    min_samples: int = Field(default=30, ge=5, le=100_000)
    window_hours: int = Field(default=24, ge=1, le=720)
    auto_retrain_on_drift: bool = False
    auto_retrain_cooldown_hours: int = Field(default=12, ge=1, le=720)


class DeploymentCreateRequest(BaseModel):
    project_id: str
    model_version_id: str
    name: str = Field(min_length=1, max_length=140)
    description: str | None = Field(default=None, max_length=2000)
    config: MonitoringConfig | None = None


class DeploymentUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=140)
    description: str | None = Field(default=None, max_length=2000)
    config: MonitoringConfig | None = None
    model_version_id: str | None = None


class DeploymentRevisionOut(BaseModel):
    id: str
    model_version_id: str
    version: int | None = None
    activated_at: datetime
    deactivated_at: datetime | None
    reason: str


class DeploymentEventOut(BaseModel):
    id: int
    level: str
    message: str
    details: dict[str, Any]
    created_at: datetime


class DeploymentSummary(BaseModel):
    id: str
    project_id: str
    name: str
    status: str
    registered_model_id: str
    model_name: str
    model_version_id: str
    model_version: int
    algorithm: str
    stage: str
    challenger_model_version_id: str | None = None
    challenger_model_version: int | None = None
    challenger_algorithm: str | None = None
    challenger_traffic_percent: int = 0
    api_key_prefix: str
    description: str | None
    last_request_at: datetime | None
    activated_at: datetime | None
    stopped_at: datetime | None
    created_at: datetime
    updated_at: datetime
    latest_monitoring_status: str | None = None
    config: MonitoringConfig


class DeploymentDetail(DeploymentSummary):
    model_metrics: dict[str, Any]
    model_params: dict[str, Any]
    problem_type: str | None
    target_column: str | None
    dataset_name: str | None
    dataset_version: int | None
    revisions: list[DeploymentRevisionOut]
    events: list[DeploymentEventOut]
    model_version_created_at: datetime


class DeploymentCreated(DeploymentDetail):
    api_key: str


class RotateKeyResponse(BaseModel):
    api_key: str
    api_key_prefix: str


class DeploymentHealthResponse(BaseModel):
    deployment_id: str
    status: str
    healthy: bool
    checks: dict[str, str | bool | None]
    checked_at: datetime


class PredictionLogOut(BaseModel):
    id: str
    deployment_id: str
    model_version_id: str
    request_id: str
    features: dict[str, Any] | None
    prediction: Any
    status: str
    variant: str = "champion"
    error_message: str | None
    latency_ms: float
    actual: Any
    actual_received_at: datetime | None
    created_at: datetime


class ChallengerUpdateRequest(BaseModel):
    model_version_id: str
    traffic_percent: int = Field(default=10, ge=1, le=80)


class ChallengerTrafficRequest(BaseModel):
    traffic_percent: int = Field(ge=0, le=80)


class ChallengerVariantStats(BaseModel):
    variant: str
    model_version_id: str
    model_version: int | None = None
    algorithm: str | None = None
    predictions: int
    failures: int
    labeled: int
    accuracy: float | None = None
    avg_latency_ms: float = 0.0
    last_prediction_at: datetime | None = None


class ChallengerInfoResponse(BaseModel):
    deployment_id: str
    champion_version_id: str
    champion_version: int
    champion_algorithm: str
    challenger_version_id: str | None = None
    challenger_version: int | None = None
    challenger_algorithm: str | None = None
    traffic_percent: int = 0
    variants: list[ChallengerVariantStats]
