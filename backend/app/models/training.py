from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin, utcnow
from app.models.enums import ExperimentStatus, JobStatus


class TrainingJob(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "training_jobs"
    __table_args__ = (
        Index("ix_training_jobs_project_created", "project_id", "created_at"),
        Index("ix_training_jobs_status", "status"),
        Index("ix_training_jobs_lease", "status", "lease_expires_at"),
        Index(
            "uq_training_jobs_idempotency",
            "project_id",
            "created_by",
            "idempotency_key",
            unique=True,
        ),
        Index("ix_training_jobs_dataset_version", "dataset_version_id"),
        Index("ix_training_jobs_retrain_source", "retrain_source_deployment_id"),
    )

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    problem_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_column: Mapped[str | None] = mapped_column(String(255), nullable=True)
    feature_columns: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    algorithms: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.QUEUED, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status_message: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    retrain_source_deployment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_token: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_attempt: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    dataset_version: Mapped[DatasetVersion] = relationship()  # noqa: F821
    project: Mapped[Project] = relationship()  # noqa: F821
    logs: Mapped[list[TrainingJobLog]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    experiments: Mapped[list[Experiment]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class TrainingDispatch(Base):
    __tablename__ = "training_dispatch"
    __table_args__ = (Index("ix_training_dispatch_due", "available_at", "job_id"),)

    job_id: Mapped[str] = mapped_column(
        ForeignKey("training_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class TrainingJobLog(Base):
    __tablename__ = "training_job_logs"
    __table_args__ = (Index("ix_training_job_logs_job_id", "job_id", "id"),)

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("training_jobs.id", ondelete="CASCADE"), nullable=False
    )
    level: Mapped[str] = mapped_column(String(10), default="info", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    job: Mapped[TrainingJob] = relationship(back_populates="logs")


class Experiment(Base, UUIDMixin):
    __tablename__ = "experiments"
    __table_args__ = (
        Index("ix_experiments_project_created", "project_id", "created_at"),
        Index("ix_experiments_job", "training_job_id"),
        Index("ix_experiments_algorithm", "algorithm"),
        Index("ix_experiments_status", "status"),
    )

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    training_job_id: Mapped[str] = mapped_column(
        ForeignKey("training_jobs.id", ondelete="CASCADE"), nullable=False
    )
    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm_label: Mapped[str] = mapped_column(String(120), nullable=False)
    problem_type: Mapped[str] = mapped_column(String(20), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    cv_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=ExperimentStatus.QUEUED, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    mlflow_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tracking_warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reference_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    training_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    job: Mapped[TrainingJob] = relationship(back_populates="experiments")
    dataset_version: Mapped[DatasetVersion] = relationship()  # noqa: F821
