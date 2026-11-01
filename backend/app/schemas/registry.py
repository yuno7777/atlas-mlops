from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ModelRegisterRequest(BaseModel):
    project_id: str
    experiment_id: str
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class ModelVersionSummary(BaseModel):
    id: str
    registered_model_id: str
    registered_model_name: str | None = None
    version: int
    experiment_id: str
    dataset_version_id: str
    algorithm: str
    framework: str
    stage: str
    metrics: dict[str, Any]
    params: dict[str, Any]
    artifact_sha256: str
    created_at: datetime
    created_by: str
    deployment_count: int = 0
    problem_type: str | None = None
    reference_feature_count: int = 0


class ModelSummary(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None
    latest_version: int
    version_count: int
    created_at: datetime
    updated_at: datetime
    latest_stage: str | None = None
    latest_metrics: dict[str, Any] | None = None
    latest_algorithm: str | None = None
    production_version: int | None = None


class ModelDetail(ModelSummary):
    versions: list[ModelVersionSummary]


class ModelVersionRegisterRequest(BaseModel):
    experiment_id: str
    description: str | None = Field(default=None, max_length=2000)


class PromoteRequest(BaseModel):
    stage: Literal["none", "staging", "production"]


class VersionCompareRequest(BaseModel):
    version_ids: list[str] = Field(min_length=2, max_length=6)


class VersionCompareResponse(BaseModel):
    metric_keys: list[str]
    directions: dict[str, str]
    best: dict[str, str]
    versions: list[ModelVersionSummary]
