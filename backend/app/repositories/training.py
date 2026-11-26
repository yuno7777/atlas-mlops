from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.dataset import DatasetVersion
from app.models.enums import JobStatus
from app.models.registry import ModelVersion
from app.models.training import Experiment, TrainingDispatch, TrainingJob, TrainingJobLog


class TrainingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_job(self, job_id: str) -> TrainingJob | None:
        return self.db.get(TrainingJob, job_id)

    def get_job_detail(self, job_id: str) -> TrainingJob | None:
        return (
            self.db.execute(
                select(TrainingJob)
                .options(
                    joinedload(TrainingJob.dataset_version).joinedload(DatasetVersion.dataset),
                    selectinload(TrainingJob.experiments),
                )
                .where(TrainingJob.id == job_id)
            )
            .unique()
            .scalar_one_or_none()
        )

    def list_jobs(
        self,
        project_id: str,
        status: str | None,
        search: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[TrainingJob], int]:
        filters = [TrainingJob.project_id == project_id]
        if status:
            filters.append(TrainingJob.status == status)
        if search:
            pattern = f"%{search.lower()}%"
            filters.append(func.lower(TrainingJob.name).like(pattern))
        total = self.db.execute(select(func.count(TrainingJob.id)).where(*filters)).scalar_one()
        items = list(
            self.db.execute(
                select(TrainingJob)
                .options(joinedload(TrainingJob.dataset_version).joinedload(DatasetVersion.dataset))
                .where(*filters)
                .order_by(TrainingJob.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .unique()
            .all()
        )
        return items, total

    def logs(self, job_id: str, after_id: int | None, limit: int = 200) -> list[TrainingJobLog]:
        query = select(TrainingJobLog).where(TrainingJobLog.job_id == job_id)
        if after_id is not None:
            query = query.where(TrainingJobLog.id > after_id)
        return list(
            self.db.execute(query.order_by(TrainingJobLog.id.asc()).limit(limit)).scalars().all()
        )

    def claim_job(self, job_id: str, now: datetime, token: str, expires: datetime) -> bool:
        result = self.db.execute(
            update(TrainingJob)
            .where(TrainingJob.id == job_id, TrainingJob.status == JobStatus.QUEUED)
            .values(
                status=JobStatus.RUNNING,
                started_at=now,
                progress=1,
                status_message="Starting",
                execution_token=token,
                lease_expires_at=expires,
                execution_attempt=TrainingJob.execution_attempt + 1,
            )
        )
        if result.rowcount != 1:
            return False
        self.clear_dispatch(job_id)
        return True

    def update_lease(self, job_id: str, token: str, expires: datetime) -> bool:
        # Evaluate expiry in the database when the row is locked. A worker may
        # have waited behind another transaction since it requested the write.
        now = (
            func.strftime("%Y-%m-%d %H:%M:%f", "now") + "000"
            if self.db.get_bind().dialect.name == "sqlite"
            else func.clock_timestamp()
        )
        result = self.db.execute(
            update(TrainingJob)
            .where(
                TrainingJob.id == job_id,
                TrainingJob.status == JobStatus.RUNNING,
                TrainingJob.execution_token == token,
                TrainingJob.lease_expires_at > now,
            )
            .values(lease_expires_at=expires)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    def clear_dispatch(self, job_id: str) -> None:
        self.db.execute(delete(TrainingDispatch).where(TrainingDispatch.job_id == job_id))

    def request_cancellation(self, job_id: str, now: datetime) -> bool:
        cancelled = self.db.execute(
            update(TrainingJob)
            .where(TrainingJob.id == job_id, TrainingJob.status == JobStatus.QUEUED)
            .values(
                status=JobStatus.CANCELLED,
                completed_at=now,
                status_message="Cancelled before execution",
            )
        )
        if cancelled.rowcount == 1:
            self.clear_dispatch(job_id)
            return True

        requested = self.db.execute(
            update(TrainingJob)
            .where(TrainingJob.id == job_id, TrainingJob.status == JobStatus.RUNNING)
            .values(cancel_requested=True, status_message="Cancellation requested")
        )
        return requested.rowcount == 1

    def add(self, entity: object) -> None:
        self.db.add(entity)
        self.db.flush()

    def active_job_count(self, project_id: str) -> int:
        return self.db.execute(
            select(func.count(TrainingJob.id)).where(
                TrainingJob.project_id == project_id,
                TrainingJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
        ).scalar_one()


class ExperimentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, experiment_id: str) -> Experiment | None:
        return self.db.get(Experiment, experiment_id)

    def list_for_job(self, job_id: str) -> list[Experiment]:
        return list(
            self.db.execute(
                select(Experiment)
                .where(Experiment.training_job_id == job_id)
                .order_by(Experiment.created_at.asc())
            )
            .scalars()
            .all()
        )

    def list(
        self,
        project_id: str,
        dataset_version_id: str | None,
        algorithm: str | None,
        status: str | None,
        problem_type: str | None,
        job_id: str | None,
        search: str | None,
        sort: str,
        offset: int,
        limit: int,
    ) -> tuple[list[Experiment], int]:
        filters = [Experiment.project_id == project_id]
        if dataset_version_id:
            filters.append(Experiment.dataset_version_id == dataset_version_id)
        if algorithm:
            filters.append(Experiment.algorithm == algorithm)
        if status:
            filters.append(Experiment.status == status)
        if problem_type:
            filters.append(Experiment.problem_type == problem_type)
        if job_id:
            filters.append(Experiment.training_job_id == job_id)
        if search:
            pattern = f"%{search.lower()}%"
            filters.append(
                or_(
                    func.lower(Experiment.name).like(pattern),
                    func.lower(Experiment.algorithm).like(pattern),
                )
            )
        total = self.db.execute(select(func.count(Experiment.id)).where(*filters)).scalar_one()

        sort_map = {
            "created_at": Experiment.created_at,
            "-created_at": Experiment.created_at.desc(),
            "name": Experiment.name,
            "-name": Experiment.name.desc(),
            "duration": Experiment.training_duration_seconds,
            "-duration": Experiment.training_duration_seconds.desc(),
        }
        order = sort_map.get(sort, Experiment.created_at.desc())
        items = list(
            self.db.execute(
                select(Experiment)
                .options(joinedload(Experiment.dataset_version).joinedload(DatasetVersion.dataset))
                .where(*filters)
                .order_by(order)
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .unique()
            .all()
        )
        return items, total

    def by_ids(self, ids: list[str]) -> list[Experiment]:
        if not ids:
            return []
        return list(
            self.db.execute(
                select(Experiment)
                .options(joinedload(Experiment.dataset_version).joinedload(DatasetVersion.dataset))
                .where(Experiment.id.in_(ids))
            )
            .scalars()
            .unique()
            .all()
        )

    def registrations_for(self, experiment_ids: list[str]) -> dict[str, ModelVersion]:
        if not experiment_ids:
            return {}
        rows = self.db.execute(
            select(ModelVersion)
            .options(joinedload(ModelVersion.registered_model))
            .where(ModelVersion.experiment_id.in_(experiment_ids))
        ).scalars()
        return {version.experiment_id: version for version in rows}
