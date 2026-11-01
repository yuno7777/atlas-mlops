"""SQLAlchemy models. Importing this module registers all tables on the metadata."""

from app.models.audit import AuditEvent
from app.models.dataset import Dataset, DatasetVersion
from app.models.deployment import (
    Deployment,
    DeploymentEvent,
    DeploymentRevision,
    PredictionLog,
)
from app.models.monitoring import MonitoringResult
from app.models.registry import ModelVersion, RegisteredModel
from app.models.training import Experiment, TrainingJob, TrainingJobLog
from app.models.user import Project, User, Workspace, WorkspaceMember

__all__ = [
    "AuditEvent",
    "Dataset",
    "DatasetVersion",
    "Deployment",
    "DeploymentEvent",
    "DeploymentRevision",
    "Experiment",
    "ModelVersion",
    "MonitoringResult",
    "PredictionLog",
    "Project",
    "RegisteredModel",
    "TrainingJob",
    "TrainingJobLog",
    "User",
    "Workspace",
    "WorkspaceMember",
]
