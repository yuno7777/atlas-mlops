from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin, utcnow
from app.models.enums import DeploymentStatus


class Deployment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "deployments"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_deployment_project_name"),
        Index("ix_deployments_status", "status"),
    )

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    registered_model_id: Mapped[str] = mapped_column(
        ForeignKey("registered_models.id", ondelete="RESTRICT"), nullable=False
    )
    model_version_id: Mapped[str] = mapped_column(
        ForeignKey("model_versions.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default=DeploymentStatus.STOPPED, nullable=False
    )
    api_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    api_key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    last_request_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_retrain_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    model_version: Mapped[ModelVersion] = relationship()  # noqa: F821
    registered_model: Mapped[RegisteredModel] = relationship()  # noqa: F821
    revisions: Mapped[list[DeploymentRevision]] = relationship(
        back_populates="deployment",
        cascade="all, delete-orphan",
        order_by="DeploymentRevision.activated_at.desc()",
    )
    events: Mapped[list[DeploymentEvent]] = relationship(
        back_populates="deployment",
        cascade="all, delete-orphan",
        order_by="DeploymentEvent.id.desc()",
    )
    predictions: Mapped[list[PredictionLog]] = relationship(
        back_populates="deployment", cascade="all, delete-orphan"
    )
    monitoring_results: Mapped[list[MonitoringResult]] = relationship(  # noqa: F821
        back_populates="deployment", cascade="all, delete-orphan"
    )


class DeploymentRevision(Base, UUIDMixin):
    __tablename__ = "deployment_revisions"
    __table_args__ = (Index("ix_deployment_revisions_deployment", "deployment_id", "activated_at"),)

    deployment_id: Mapped[str] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False
    )
    model_version_id: Mapped[str] = mapped_column(
        ForeignKey("model_versions.id", ondelete="RESTRICT"), nullable=False
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str] = mapped_column(String(64), default="initial", nullable=False)
    created_by: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    deployment: Mapped[Deployment] = relationship(back_populates="revisions")
    model_version: Mapped[ModelVersion] = relationship()  # noqa: F821


class DeploymentEvent(Base):
    __tablename__ = "deployment_events"
    __table_args__ = (Index("ix_deployment_events_deployment", "deployment_id", "id"),)

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    deployment_id: Mapped[str] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False
    )
    level: Mapped[str] = mapped_column(String(10), default="info", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    deployment: Mapped[Deployment] = relationship(back_populates="events")


class PredictionLog(Base, UUIDMixin):
    __tablename__ = "prediction_logs"
    __table_args__ = (
        Index("ix_prediction_logs_deployment_created", "deployment_id", "created_at"),
        Index("ix_prediction_logs_deployment_status", "deployment_id", "status", "created_at"),
        Index("ix_prediction_logs_created", "created_at"),
    )

    deployment_id: Mapped[str] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False
    )
    model_version_id: Mapped[str] = mapped_column(
        ForeignKey("model_versions.id", ondelete="RESTRICT"), nullable=False
    )
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    features: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    prediction: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="success", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    actual: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    actual_received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    deployment: Mapped[Deployment] = relationship(back_populates="predictions")
