from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.monitoring import MonitoringResult


class MonitoringRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def latest(self, deployment_id: str) -> MonitoringResult | None:
        return self.db.execute(
            select(MonitoringResult)
            .where(MonitoringResult.deployment_id == deployment_id)
            .order_by(MonitoringResult.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def list(
        self, deployment_id: str, offset: int, limit: int
    ) -> tuple[list[MonitoringResult], int]:
        from sqlalchemy import func

        total = self.db.execute(
            select(func.count(MonitoringResult.id)).where(
                MonitoringResult.deployment_id == deployment_id
            )
        ).scalar_one()
        items = list(
            self.db.execute(
                select(MonitoringResult)
                .where(MonitoringResult.deployment_id == deployment_id)
                .order_by(MonitoringResult.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return items, total

    def add(self, entity: object) -> None:
        self.db.add(entity)
        self.db.flush()
