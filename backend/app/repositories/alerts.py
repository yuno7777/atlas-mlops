from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alerting import AlertChannel, AlertDelivery


class AlertRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add_channel(self, channel: AlertChannel) -> AlertChannel:
        self.db.add(channel)
        self.db.flush()
        return channel

    def get_channel(self, channel_id: str) -> AlertChannel | None:
        return self.db.get(AlertChannel, channel_id)

    def list_channels(self, project_id: str) -> list[AlertChannel]:
        return list(
            self.db.execute(
                select(AlertChannel)
                .where(AlertChannel.project_id == project_id)
                .order_by(AlertChannel.created_at.asc())
            )
            .scalars()
            .all()
        )

    def list_enabled_channels(self, project_id: str) -> list[AlertChannel]:
        return list(
            self.db.execute(
                select(AlertChannel).where(
                    AlertChannel.project_id == project_id,
                    AlertChannel.enabled.is_(True),
                )
            )
            .scalars()
            .all()
        )

    def add_delivery(self, delivery: AlertDelivery) -> AlertDelivery:
        self.db.add(delivery)
        self.db.flush()
        return delivery

    def recent_deliveries(
        self, channel_ids: list[str], limit: int = 3
    ) -> dict[str, list[AlertDelivery]]:
        if not channel_ids:
            return {}
        rows = self.db.execute(
            select(AlertDelivery)
            .where(AlertDelivery.channel_id.in_(channel_ids))
            .order_by(AlertDelivery.created_at.desc())
        ).scalars()
        grouped: dict[str, list[AlertDelivery]] = {channel_id: [] for channel_id in channel_ids}
        for delivery in rows:
            bucket = grouped.setdefault(delivery.channel_id, [])
            if len(bucket) < limit:
                bucket.append(delivery)
        return grouped
