from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.dataset import Dataset, DatasetVersion
from app.models.registry import ModelVersion
from app.models.training import TrainingJob


class DatasetRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, dataset_id: str) -> Dataset | None:
        return self.db.get(Dataset, dataset_id)

    def get_by_name(self, project_id: str, name: str) -> Dataset | None:
        return self.db.execute(
            select(Dataset).where(Dataset.project_id == project_id, Dataset.name == name)
        ).scalar_one_or_none()

    def list_for_project(
        self, project_id: str, search: str | None, offset: int, limit: int
    ) -> tuple[list[Dataset], int]:
        filters = [Dataset.project_id == project_id]
        if search:
            pattern = f"%{search.lower()}%"
            filters.append(
                or_(
                    func.lower(Dataset.name).like(pattern),
                    func.lower(Dataset.description).like(pattern),
                )
            )
        total = self.db.execute(select(func.count(Dataset.id)).where(*filters)).scalar_one()
        items = list(
            self.db.execute(
                select(Dataset)
                .where(*filters)
                .order_by(Dataset.updated_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return items, total

    def versions_for_datasets(self, dataset_ids: list[str]) -> dict[str, list[DatasetVersion]]:
        if not dataset_ids:
            return {}
        rows = self.db.execute(
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id.in_(dataset_ids))
            .order_by(DatasetVersion.version.desc())
        ).scalars()
        result: dict[str, list[DatasetVersion]] = {}
        for version in rows:
            result.setdefault(version.dataset_id, []).append(version)
        return result

    def list_versions(self, dataset_id: str) -> list[DatasetVersion]:
        return list(
            self.db.execute(
                select(DatasetVersion)
                .where(DatasetVersion.dataset_id == dataset_id)
                .order_by(DatasetVersion.version.desc())
            )
            .scalars()
            .all()
        )

    def latest_version(self, dataset_id: str) -> DatasetVersion | None:
        return self.db.execute(
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.version.desc())
            .limit(1)
        ).scalar_one_or_none()

    def get_version(self, version_id: str) -> DatasetVersion | None:
        return self.db.execute(
            select(DatasetVersion)
            .options(selectinload(DatasetVersion.dataset))
            .where(DatasetVersion.id == version_id)
        ).scalar_one_or_none()

    def find_checksum(self, dataset_id: str, checksum: str) -> DatasetVersion | None:
        return self.db.execute(
            select(DatasetVersion).where(
                DatasetVersion.dataset_id == dataset_id,
                DatasetVersion.checksum == checksum,
            )
        ).scalar_one_or_none()

    def next_version_number(self, dataset_id: str) -> int:
        current = self.db.execute(
            select(func.max(DatasetVersion.version)).where(DatasetVersion.dataset_id == dataset_id)
        ).scalar_one()
        return int(current or 0) + 1

    def add(self, entity: object) -> None:
        self.db.add(entity)
        self.db.flush()

    def jobs_referencing(self, dataset_id: str) -> int:
        return self.db.execute(
            select(func.count(TrainingJob.id))
            .join(DatasetVersion, DatasetVersion.id == TrainingJob.dataset_version_id)
            .where(DatasetVersion.dataset_id == dataset_id)
        ).scalar_one()

    def model_versions_referencing(self, dataset_id: str) -> int:
        return self.db.execute(
            select(func.count(ModelVersion.id))
            .join(DatasetVersion, DatasetVersion.id == ModelVersion.dataset_version_id)
            .where(DatasetVersion.dataset_id == dataset_id)
        ).scalar_one()

    def delete(self, dataset: Dataset) -> None:
        self.db.delete(dataset)
