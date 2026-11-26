"""SQLAlchemy models. Importing this module registers all tables on the metadata."""

from app.models.alerting import AlertChannel, AlertDelivery
from app.models.audit import AuditEvent
from app.models.batch import BatchPrediction
from app.models.collaboration import WorkspaceInvite
from app.models.dataset import Dataset, DatasetVersion
from app.models.deployment import (
    Deployment,
    DeploymentEvent,
    DeploymentRevision,
    PredictionLog,
)
from app.models.modelops import DeploymentRollout, WorkflowRun
from app.models.monitoring import MonitoringResult
from app.models.registry import ModelVersion, RegisteredModel
from app.models.training import Experiment, TrainingDispatch, TrainingJob, TrainingJobLog
from app.models.user import Project, User, Workspace, WorkspaceMember

__all__ = [
    "AlertChannel",
    "AlertDelivery",
    "AuditEvent",
    "BatchPrediction",
    "Dataset",
    "DatasetVersion",
    "Deployment",
    "DeploymentEvent",
    "DeploymentRevision",
    "DeploymentRollout",
    "Experiment",
    "ModelVersion",
    "MonitoringResult",
    "PredictionLog",
    "Project",
    "RegisteredModel",
    "TrainingDispatch",
    "TrainingJob",
    "TrainingJobLog",
    "User",
    "Workspace",
    "WorkspaceInvite",
    "WorkspaceMember",
    "WorkflowRun",
]
