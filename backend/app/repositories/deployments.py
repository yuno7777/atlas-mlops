from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, func, select
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
                    joinedload(Deployment.challenger_model_version).joinedload(
                        ModelVersion.registered_model
                    ),
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
                    joinedload(Deployment.challenger_model_version).joinedload(
                        ModelVersion.registered_model
                    ),
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
                    joinedload(Deployment.challenger_model_version).joinedload(
                        ModelVersion.registered_model
                    ),
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

    def predictions_since(
        self,
        deployment_id: str,
        since: datetime,
        *,
        variant: str | None = None,
        model_version_id: str | None = None,
    ) -> list[PredictionLog]:
        filters = [
            PredictionLog.deployment_id == deployment_id,
            PredictionLog.created_at >= since,
        ]
        if variant:
            filters.append(PredictionLog.variant == variant)
        if model_version_id:
            filters.append(PredictionLog.model_version_id == model_version_id)
        return list(
            self.db.execute(
                select(PredictionLog).where(*filters).order_by(PredictionLog.created_at.asc())
            )
            .scalars()
            .all()
        )

    def variant_overview(self, deployment_id: str) -> list[dict]:
        rows = self.db.execute(
            select(
                PredictionLog.variant,
                PredictionLog.model_version_id,
                func.count(PredictionLog.id),
                func.sum(case((PredictionLog.status == "failed", 1), else_=0)),
                func.sum(case((PredictionLog.actual.is_not(None), 1), else_=0)),
                func.avg(PredictionLog.latency_ms),
                func.max(PredictionLog.created_at),
            )
            .where(PredictionLog.deployment_id == deployment_id)
            .group_by(PredictionLog.variant, PredictionLog.model_version_id)
        ).all()
        return [
            {
                "variant": row[0],
                "model_version_id": row[1],
                "predictions": int(row[2] or 0),
                "failures": int(row[3] or 0),
                "labeled": int(row[4] or 0),
                "avg_latency_ms": float(row[5] or 0.0),
                "last_prediction_at": row[6],
            }
            for row in rows
        ]

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
