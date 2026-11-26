from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.experiment import ExperimentSummary


class HyperparameterOut(BaseModel):
    name: str
    label: str
    type: str
    default: Any
    min: float | None = None
    max: float | None = None
    step: float | None = None
    choices: list[str] | None = None
    description: str = ""


class AlgorithmOut(BaseModel):
    id: str
    label: str
    problem_type: str
    description: str
    framework: str
    supports_cv: bool
    hyperparameters: list[HyperparameterOut]


class AlgorithmSelection(BaseModel):
    algorithm: str = Field(min_length=1, max_length=64)
    hyperparameters: dict[str, Any] = Field(default_factory=dict)


class TrainingExecutionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: int = Field(default=6900, ge=1, le=6900, strict=True)
    cancel_grace_seconds: int = Field(default=30, ge=1, le=300, strict=True)
    max_attempts: int | None = Field(default=None, ge=1, le=5, strict=True)
    retry_backoff_seconds: int = Field(default=5, ge=1, le=300, strict=True)


class TrainingJobCreateRequest(BaseModel):
    project_id: str
    dataset_version_id: str
    name: str | None = Field(default=None, max_length=160)
    problem_type: Literal["classification", "regression", "clustering"]
    target_column: str | None = Field(default=None, max_length=255)
    feature_columns: list[str] | None = None
    sensitive_columns: list[str] = Field(default_factory=list, max_length=12)
    algorithms: list[AlgorithmSelection] = Field(min_length=1, max_length=10)
    test_size: float = Field(default=0.2, ge=0.1, le=0.4)
    random_seed: int = Field(default=42, ge=0, le=2_147_483_647)
    cv_folds: int = Field(default=0, ge=0, le=10)
    register_model_name: str | None = Field(default=None, max_length=120)
    execution_policy: TrainingExecutionPolicy | None = None
    workflow_run_id: str | None = Field(default=None, exclude=True)

    @field_validator("feature_columns")
    @classmethod
    def unique_features(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("feature_columns must contain at least one column")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("feature_columns contains duplicates")
        return cleaned

    @field_validator("sensitive_columns")
    @classmethod
    def unique_sensitive_columns(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("sensitive_columns contains duplicates")
        return cleaned

    @field_validator("target_column")
    @classmethod
    def clean_target(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("register_model_name")
    @classmethod
    def clean_model_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class TrainingJobSummary(BaseModel):
    id: str
    project_id: str
    name: str
    problem_type: str
    status: str
    progress: int
    status_message: str | None
    dataset_version_id: str
    dataset_name: str
    dataset_version: int
    target_column: str | None
    algorithm_count: int
    retrain_source_deployment_id: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: float | None


class TrainingJobDetail(TrainingJobSummary):
    feature_columns: list[str] | None
    algorithms: list[dict[str, Any]]
    config: dict[str, Any]
    error_message: str | None
    cancel_requested: bool
    execution_attempt: int = 0
    execution_deadline_at: datetime | None = None
    cancel_deadline_at: datetime | None = None
    experiments: list[ExperimentSummary]
    created_by: str


class TrainingJobLogOut(BaseModel):
    id: int
    level: str
    message: str
    created_at: datetime


class TrainingJobLogsResponse(BaseModel):
    items: list[TrainingJobLogOut]
    last_id: int | None
