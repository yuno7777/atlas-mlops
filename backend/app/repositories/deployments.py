from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.deployment import (
    Deployment,
    DeploymentEvent,
    DeploymentRevision,
    PredictionLog,
)
from app.models.monitoring import MonitoringResult
from app.models.registry import ModelVersion


class DeploymentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, deployment_id: str) -> Deployment | None:
        return (
            self.db.execute(
                select(Deployment)
                .options(
                    joinedload(Deployment.model_version).joinedload(ModelVersion.registered_model),
                    joinedload(Deployment.registered_model),
                )
                .where(Deployment.id == deployment_id)
            )
            .unique()
            .scalar_one_or_none()
        )

    def get_detail(self, deployment_id: str) -> Deployment | None:
        return (
            self.db.execute(
                select(Deployment)
                .options(
                    joinedload(Deployment.model_version).joinedload(ModelVersion.registered_model),
                    joinedload(Deployment.registered_model),
                    selectinload(Deployment.revisions).joinedload(DeploymentRevision.model_version),
                    selectinload(Deployment.events),
                )
                .where(Deployment.id == deployment_id)
            )
            .unique()
            .scalar_one_or_none()
        )

    def get_by_name(self, project_id: str, name: str) -> Deployment | None:
        return self.db.execute(
            select(Deployment).where(Deployment.project_id == project_id, Deployment.name == name)
        ).scalar_one_or_none()

    def list(
        self, project_id: str, status: str | None, offset: int, limit: int
    ) -> tuple[list[Deployment], int]:
        filters = [Deployment.project_id == project_id]
        if status:
            filters.append(Deployment.status == status)
        total = self.db.execute(select(func.count(Deployment.id)).where(*filters)).scalar_one()
        items = list(
            self.db.execute(
                select(Deployment)
                .options(
                    joinedload(Deployment.model_version).joinedload(ModelVersion.registered_model),
                    joinedload(Deployment.registered_model),
                )
                .where(*filters)
                .order_by(Deployment.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .unique()
            .all()
        )
        return items, total

    def list_all_active(self) -> list[Deployment]:
        return list(
            self.db.execute(select(Deployment).where(Deployment.status == "active")).scalars().all()
        )

    def latest_monitoring_for(self, deployment_ids: list[str]) -> dict[str, MonitoringResult]:
        if not deployment_ids:
            return {}
        results = list(
            self.db.execute(
                select(MonitoringResult)
                .where(MonitoringResult.deployment_id.in_(deployment_ids))
                .order_by(MonitoringResult.created_at.desc())
            )
            .scalars()
            .all()
        )
        latest: dict[str, MonitoringResult] = {}
        for result in results:
            latest.setdefault(result.deployment_id, result)
        return latest

    def revisions(self, deployment_id: str) -> list[DeploymentRevision]:
        return list(
            self.db.execute(
                select(DeploymentRevision)
                .options(joinedload(DeploymentRevision.model_version))
                .where(DeploymentRevision.deployment_id == deployment_id)
                .order_by(DeploymentRevision.activated_at.desc())
            )
            .scalars()
            .unique()
            .all()
        )

    def events(self, deployment_id: str, limit: int = 50) -> list[DeploymentEvent]:
        return list(
            self.db.execute(
                select(DeploymentEvent)
                .where(DeploymentEvent.deployment_id == deployment_id)
                .order_by(DeploymentEvent.id.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )

    def predictions(
        self,
        deployment_id: str,
        status: str | None,
        start: datetime | None,
        end: datetime | None,
        offset: int,
        limit: int,
    ) -> tuple[list[PredictionLog], int]:
        filters = [PredictionLog.deployment_id == deployment_id]
        if status:
            filters.append(PredictionLog.status == status)
        if start:
            filters.append(PredictionLog.created_at >= start)
        if end:
            filters.append(PredictionLog.created_at <= end)
        total = self.db.execute(select(func.count(PredictionLog.id)).where(*filters)).scalar_one()
        items = list(
            self.db.execute(
                select(PredictionLog)
                .where(*filters)
                .order_by(PredictionLog.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return items, total

    def predictions_since(self, deployment_id: str, since: datetime) -> list[PredictionLog]:
        return list(
            self.db.execute(
                select(PredictionLog)
                .where(
                    PredictionLog.deployment_id == deployment_id,
                    PredictionLog.created_at >= since,
                )
                .order_by(PredictionLog.created_at.asc())
            )
            .scalars()
            .all()
        )

    def get_prediction(self, prediction_id: str) -> PredictionLog | None:
        return self.db.get(PredictionLog, prediction_id)

    def prediction_count_for_project(self, project_id: str, since: datetime) -> int:
        return self.db.execute(
            select(func.count(PredictionLog.id))
            .join(Deployment, Deployment.id == PredictionLog.deployment_id)
            .where(Deployment.project_id == project_id, PredictionLog.created_at >= since)
        ).scalar_one()

    def add(self, entity: object) -> None:
        self.db.add(entity)
        self.db.flush()
