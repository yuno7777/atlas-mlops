from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


ROLE_RANK: dict[str, int] = {
    Role.VIEWER: 1,
    Role.MEMBER: 2,
    Role.ADMIN: 3,
    Role.OWNER: 4,
}


class ProblemType(StrEnum):
    CLASSIFICATION = "classification"
    REGRESSION = "regression"
    CLUSTERING = "clustering"


class DatasetStatus(StrEnum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExperimentStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelStage(StrEnum):
    NONE = "none"
    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"


class DeploymentStatus(StrEnum):
    ACTIVE = "active"
    STOPPED = "stopped"
    FAILED = "failed"


class MonitoringStatus(StrEnum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    INSUFFICIENT_DATA = "insufficient_data"


PROBLEM_TYPE_LABELS = {
    ProblemType.CLASSIFICATION: "Classification",
    ProblemType.REGRESSION: "Regression",
    ProblemType.CLUSTERING: "Clustering",
}
