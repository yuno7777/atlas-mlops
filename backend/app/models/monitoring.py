from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDMixin, utcnow


class MonitoringResult(Base, UUIDMixin):
    __tablename__ = "monitoring_results"
    __table_args__ = (
        Index("ix_monitoring_results_deployment_created", "deployment_id", "created_at"),
    )

    deployment_id: Mapped[str] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False
    )
    model_version_id: Mapped[str] = mapped_column(
        ForeignKey("model_versions.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    labeled_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    data_drift_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    prediction_drift_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    concept_drift_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    drift_share: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    psi_max: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    ks_min_pvalue: Mapped[float | None] = mapped_column(Float, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    deployment: Mapped[Deployment] = relationship(  # noqa: F821
        back_populates="monitoring_results"
    )
