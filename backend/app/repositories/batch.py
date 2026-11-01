from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.batch import BatchPrediction


class BatchPredictionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, batch: BatchPrediction) -> BatchPrediction:
        self.db.add(batch)
        self.db.flush()
        return batch

    def get(self, batch_id: str) -> BatchPrediction | None:
        return self.db.get(BatchPrediction, batch_id)

    def list_for_deployment(self, deployment_id: str, limit: int = 25) -> list[BatchPrediction]:
        return list(
            self.db.execute(
                select(BatchPrediction)
                .where(BatchPrediction.deployment_id == deployment_id)
                .order_by(BatchPrediction.created_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
