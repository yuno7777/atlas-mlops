from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.training import AlgorithmSelection


class ReleaseGates(BaseModel):
    min_samples: int = Field(default=100, ge=10, le=1_000_000)
    max_error_rate: float = Field(default=0.02, ge=0, le=1)
    max_p95_latency_ms: float = Field(default=1000, gt=0, le=300_000)
    min_labeled_samples: int = Field(default=20, ge=0, le=100_000)
    max_metric_regression: float = Field(default=0.03, ge=0, le=1)


class RolloutStartRequest(BaseModel):
    model_version_id: str | None = None
    traffic_steps: list[int] = Field(
        default_factory=lambda: [5, 20, 50, 100], min_length=2, max_length=8
    )
    gates: ReleaseGates = Field(default_factory=ReleaseGates)

    @field_validator("traffic_steps")
    @classmethod
    def ordered_traffic_steps(cls, value: list[int]) -> list[int]:
        if any(not 1 <= step <= 100 for step in value):
            raise ValueError("Traffic steps must be between 1 and 100 percent.")
        if value != sorted(set(value)) or value[-1] != 100:
            raise ValueError("Traffic steps must increase strictly and finish at 100 percent.")
        return value


class RolloutResponse(BaseModel):
    id: str
    deployment_id: str
    candidate_version_id: str
    status: str
    traffic_steps: list[int]
    current_step: int
    current_traffic_percent: int
    gates: dict[str, Any]
    last_evaluation: dict[str, Any]
    started_at: datetime
    step_started_at: datetime
    last_evaluated_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class FairnessColumnReport(BaseModel):
    groups: dict[str, dict[str, Any]]
    group_count: int
    smallest_group_samples: int
    selection_rate_gap: float | None = None
    accuracy_gap: float | None = None
    mae_gap: float | None = None
    positive_class: str | None = None


class ModelCardResponse(BaseModel):
    schema_version: str
    model: dict[str, Any]
    intended_use: dict[str, Any]
    training_data: dict[str, Any]
    evaluation: dict[str, Any]
    fairness: dict[str, Any] | None
    limitations: list[str]
    monitoring: dict[str, Any]
    provenance: dict[str, Any]


class PipelineTemplate(BaseModel):
    id: str
    name: str
    problem_type: str
    summary: str
    metric_keys: list[str]
    algorithms: list[AlgorithmSelection]
    steps: list[dict[str, Any]]
    protocol: dict[str, Any]


class PipelineRunCreate(BaseModel):
    project_id: str
    dataset_version_id: str
    template_id: str
    target_column: str | None = Field(default=None, max_length=255)
    feature_columns: list[str] | None = None
    sensitive_columns: list[str] = Field(default_factory=list, max_length=12)
    test_size: float = Field(default=0.2, ge=0.1, le=0.4)
    random_seed: int = Field(default=42, ge=0, le=2_147_483_647)
    cv_folds: int = Field(default=3, ge=2, le=10)
    register_model_name: str | None = Field(default=None, max_length=120)
    cache_enabled: bool = True
    max_attempts: int = Field(default=2, ge=1, le=5)
    scheduled_at: datetime | None = None
    name: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def clustering_protocol(self) -> PipelineRunCreate:
        if self.sensitive_columns and self.target_column is None:
            raise ValueError("Sensitive audit columns require a supervised target.")
        return self


class PipelineRunResponse(BaseModel):
    id: str
    project_id: str
    dataset_version_id: str
    training_job_id: str | None
    parent_run_id: str | None
    template_id: str
    name: str
    status: str
    step_states: list[dict[str, Any]]
    config: dict[str, Any]
    cache_hit: bool
    attempt: int
    max_attempts: int
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    created_at: datetime
    experiments: list[dict[str, Any]] = Field(default_factory=list)


class BenchmarkReportResponse(BaseModel):
    training_job_id: str
    name: str
    dataset_name: str
    dataset_version: int
    dataset_version_id: str
    problem_type: str
    status: str
    protocol: dict[str, Any]
    experiments: list[dict[str, Any]]
    created_at: datetime


class SLOSnapshot(BaseModel):
    window: str
    requests: int
    server_errors: int
    availability: float | None
    availability_target: float
    availability_error_budget_percent_used: float | None
    latency_sli: float | None
    latency_target_ms: float
    latency_target: float
    p95_latency_ms: float | None
    status: Literal["no_data", "met", "at_risk", "breached"]
    trace_export_enabled: bool
    trace_export_endpoint: str | None
