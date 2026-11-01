from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin, utcnow
from app.models.enums import ModelStage


class RegisteredModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "registered_models"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_registered_model_project_name"),
    )

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    versions: Mapped[list[ModelVersion]] = relationship(
        back_populates="registered_model",
        cascade="all, delete-orphan",
        order_by="ModelVersion.version.desc()",
    )


class ModelVersion(Base, UUIDMixin):
    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint("registered_model_id", "version", name="uq_model_version"),
        UniqueConstraint(
            "registered_model_id", "experiment_id", name="uq_model_version_experiment"
        ),
        Index("ix_model_versions_model_stage", "registered_model_id", "stage"),
    )

    registered_model_id: Mapped[str] = mapped_column(
        ForeignKey("registered_models.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    experiment_id: Mapped[str] = mapped_column(
        ForeignKey("experiments.id", ondelete="RESTRICT"), nullable=False
    )
    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="RESTRICT"), nullable=False
    )
    algorithm: Mapped[str] = mapped_column(String(64), nullable=False)
    framework: Mapped[str] = mapped_column(String(40), nullable=False)
    stage: Mapped[str] = mapped_column(String(16), default=ModelStage.NONE, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    artifact_key: Mapped[str] = mapped_column(String(500), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    registered_model: Mapped[RegisteredModel] = relationship(back_populates="versions")
    experiment: Mapped[Experiment] = relationship()  # noqa: F821
    dataset_version: Mapped[DatasetVersion] = relationship()  # noqa: F821
