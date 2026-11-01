from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin, utcnow


class Dataset(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_dataset_project_name"),)

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="datasets")  # noqa: F821
    versions: Mapped[list[DatasetVersion]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="DatasetVersion.version.desc()",
    )


class DatasetVersion(Base, UUIDMixin):
    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "version", name="uq_dataset_version"),)

    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="ready", nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    schema_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    profile_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    preview_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    validation_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    dataset: Mapped[Dataset] = relationship(back_populates="versions")
