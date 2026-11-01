from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.deployment import Deployment
from app.models.registry import ModelVersion, RegisteredModel


class RegistryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_model(self, model_id: str) -> RegisteredModel | None:
        return self.db.get(RegisteredModel, model_id)

    def get_model_detail(self, model_id: str) -> RegisteredModel | None:
        return self.db.execute(
            select(RegisteredModel)
            .options(selectinload(RegisteredModel.versions))
            .where(RegisteredModel.id == model_id)
        ).scalar_one_or_none()

    def get_by_name(self, project_id: str, name: str) -> RegisteredModel | None:
        return self.db.execute(
            select(RegisteredModel).where(
                RegisteredModel.project_id == project_id, RegisteredModel.name == name
            )
        ).scalar_one_or_none()

    def list_models(
        self, project_id: str, search: str | None, offset: int, limit: int
    ) -> tuple[list[RegisteredModel], int]:
        filters = [RegisteredModel.project_id == project_id]
        if search:
            pattern = f"%{search.lower()}%"
            filters.append(
                or_(
                    func.lower(RegisteredModel.name).like(pattern),
                    func.lower(RegisteredModel.description).like(pattern),
                )
            )
        total = self.db.execute(select(func.count(RegisteredModel.id)).where(*filters)).scalar_one()
        items = list(
            self.db.execute(
                select(RegisteredModel)
                .options(selectinload(RegisteredModel.versions))
                .where(*filters)
                .order_by(RegisteredModel.updated_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return items, total

    def get_version(self, version_id: str) -> ModelVersion | None:
        return self.db.execute(
            select(ModelVersion)
            .options(
                joinedload(ModelVersion.registered_model),
                joinedload(ModelVersion.experiment),
            )
            .where(ModelVersion.id == version_id)
        ).scalar_one_or_none()

    def get_version_with_deployments(self, version_id: str) -> ModelVersion | None:
        return self.db.execute(
            select(ModelVersion)
            .options(
                joinedload(ModelVersion.registered_model),
                joinedload(ModelVersion.experiment),
            )
            .where(ModelVersion.id == version_id)
        ).scalar_one_or_none()

    def list_versions(self, model_id: str) -> list[ModelVersion]:
        return list(
            self.db.execute(
                select(ModelVersion)
                .where(ModelVersion.registered_model_id == model_id)
                .order_by(ModelVersion.version.desc())
            )
            .scalars()
            .all()
        )

    def versions_by_ids(self, ids: list[str]) -> list[ModelVersion]:
        if not ids:
            return []
        return list(
            self.db.execute(select(ModelVersion).where(ModelVersion.id.in_(ids))).scalars().all()
        )

    def next_version_number(self, model_id: str) -> int:
        current = self.db.execute(
            select(func.max(ModelVersion.version)).where(
                ModelVersion.registered_model_id == model_id
            )
        ).scalar_one()
        return int(current or 0) + 1

    def version_for_experiment(self, model_id: str, experiment_id: str) -> ModelVersion | None:
        return self.db.execute(
            select(ModelVersion).where(
                ModelVersion.registered_model_id == model_id,
                ModelVersion.experiment_id == experiment_id,
            )
        ).scalar_one_or_none()

    def deployment_counts(self, version_ids: list[str]) -> dict[str, int]:
        if not version_ids:
            return {}
        rows = self.db.execute(
            select(Deployment.model_version_id, func.count(Deployment.id))
            .where(Deployment.model_version_id.in_(version_ids))
            .group_by(Deployment.model_version_id)
        ).all()
        return dict(rows)

    def add(self, entity: object) -> None:
        self.db.add(entity)
        self.db.flush()
