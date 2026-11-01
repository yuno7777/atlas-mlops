from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin, utcnow


class AlertChannel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "alert_channels"
    __table_args__ = (Index("ix_alert_channels_project", "project_id", "created_at"),)

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="webhook", nullable=False)
    target_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    min_status: Mapped[str] = mapped_column(String(16), default="warning", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    deliveries: Mapped[list[AlertDelivery]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )


class AlertDelivery(Base, UUIDMixin):
    __tablename__ = "alert_deliveries"
    __table_args__ = (Index("ix_alert_deliveries_channel", "channel_id", "created_at"),)

    channel_id: Mapped[str] = mapped_column(
        ForeignKey("alert_channels.id", ondelete="CASCADE"), nullable=False
    )
    deployment_id: Mapped[str] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False
    )
    monitoring_result_id: Mapped[str | None] = mapped_column(
        ForeignKey("monitoring_results.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), default="sent", nullable=False)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    channel: Mapped[AlertChannel] = relationship(back_populates="deliveries")
