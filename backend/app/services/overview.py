from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.ml.evaluation import METRIC_DIRECTIONS, primary_metric
from app.ml.utils import float_or_none
from app.models.dataset import Dataset, DatasetVersion
from app.models.deployment import Deployment
from app.models.enums import ExperimentStatus, JobStatus
from app.models.registry import ModelVersion, RegisteredModel
from app.models.training import Experiment, TrainingJob
from app.models.user import User
from app.repositories.audit import AuditRepository
from app.repositories.deployments import DeploymentRepository
from app.schemas.overview import (
    DeploymentHealthItem,
    LatestModelItem,
    ModelPerformanceItem,
    OverviewCounts,
    OverviewResponse,
    PerformancePoint,
    RecentEventItem,
    RecentJobItem,
    TrainingActivityPoint,
)
from app.services.access import require_project


def _count(db: Session, statement) -> int:
    return int(db.execute(statement).scalar_one() or 0)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def get_overview(db: Session, user: User, project_id: str) -> OverviewResponse:
    project, _role = require_project(db, user, project_id)
    window_start = datetime.now(UTC) - timedelta(days=7)

    dataset_filter = Dataset.project_id == project.id
    counts = OverviewCounts(
        datasets=_count(db, select(func.count(Dataset.id)).where(dataset_filter)),
        dataset_versions=_count(
            db,
            select(func.count(DatasetVersion.id))
            .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
            .where(dataset_filter),
        ),
        experiments=_count(
            db, select(func.count(Experiment.id)).where(Experiment.project_id == project.id)
        ),
        completed_experiments=_count(
            db,
            select(func.count(Experiment.id)).where(
                Experiment.project_id == project.id,
                Experiment.status == ExperimentStatus.COMPLETED,
            ),
        ),
        registered_models=_count(
            db,
            select(func.count(RegisteredModel.id)).where(RegisteredModel.project_id == project.id),
        ),
        model_versions=_count(
            db,
            select(func.count(ModelVersion.id))
            .join(RegisteredModel, RegisteredModel.id == ModelVersion.registered_model_id)
            .where(RegisteredModel.project_id == project.id),
        ),
        active_deployments=_count(
            db,
            select(func.count(Deployment.id)).where(
                Deployment.project_id == project.id,
                Deployment.status == "active",
            ),
        ),
        training_jobs=_count(
            db, select(func.count(TrainingJob.id)).where(TrainingJob.project_id == project.id)
        ),
        predictions_7d=DeploymentRepository(db).prediction_count_for_project(
            project.id, window_start
        ),
    )

    activity_start = (datetime.now(UTC) - timedelta(days=13)).date()
    activity_rows = db.execute(
        select(TrainingJob.created_at, TrainingJob.status).where(
            TrainingJob.project_id == project.id,
            TrainingJob.created_at >= datetime.combine(activity_start, datetime.min.time()),
        )
    ).all()
    activity_map: dict[date, dict[str, int]] = defaultdict(
        lambda: {"completed": 0, "failed": 0, "running": 0, "total": 0}
    )
    for created_at, status in activity_rows:
        day = _utc(created_at).date()
        bucket = activity_map[day]
        bucket["total"] += 1
        if status == JobStatus.COMPLETED:
            bucket["completed"] += 1
        elif status == JobStatus.FAILED:
            bucket["failed"] += 1
        elif status == JobStatus.RUNNING:
            bucket["running"] += 1
    training_activity = [
        TrainingActivityPoint(
            date=activity_start + timedelta(days=offset),
            completed=activity_map[activity_start + timedelta(days=offset)]["completed"],
            failed=activity_map[activity_start + timedelta(days=offset)]["failed"],
            running=activity_map[activity_start + timedelta(days=offset)]["running"],
            total=activity_map[activity_start + timedelta(days=offset)]["total"],
        )
        for offset in range(14)
    ]

    completed_experiments = list(
        db.execute(
            select(Experiment)
            .where(
                Experiment.project_id == project.id,
                Experiment.status == ExperimentStatus.COMPLETED,
            )
            .order_by(Experiment.created_at.desc())
            .limit(80)
        )
        .scalars()
        .all()
    )
    performance_points: list[PerformancePoint] = []
    for experiment in sorted(completed_experiments[:30], key=lambda item: item.created_at):
        metric = primary_metric(experiment.problem_type)
        value = float_or_none(experiment.metrics.get(metric))
        if value is None:
            continue
        performance_points.append(
            PerformancePoint(
                date=_utc(experiment.created_at),
                experiment_id=experiment.id,
                name=experiment.name,
                algorithm=experiment.algorithm,
                primary_metric=metric,
                value=value,
                problem_type=experiment.problem_type,
            )
        )

    grouped: dict[str, list[Experiment]] = defaultdict(list)
    for experiment in completed_experiments:
        grouped[experiment.algorithm].append(experiment)
    model_performance: list[ModelPerformanceItem] = []
    for algorithm, items in grouped.items():
        label = items[0].algorithm_label
        problem = items[0].problem_type
        metric = primary_metric(problem)
        direction = METRIC_DIRECTIONS.get(metric, "max")
        values = [
            value
            for value in (float_or_none(item.metrics.get(metric)) for item in items)
            if value is not None
        ]
        if not values:
            continue
        model_performance.append(
            ModelPerformanceItem(
                algorithm=algorithm,
                algorithm_label=label,
                runs=len(items),
                primary_metric=metric,
                average=sum(values) / len(values),
                best=(max(values) if direction == "max" else min(values)),
            )
        )
    model_performance.sort(key=lambda item: item.runs, reverse=True)

    deployments = list(
        db.execute(
            select(Deployment)
            .options(joinedload(Deployment.model_version).joinedload(ModelVersion.registered_model))
            .where(Deployment.project_id == project.id)
            .order_by(Deployment.created_at.desc())
        )
        .scalars()
        .unique()
        .all()
    )
    latest_monitoring = DeploymentRepository(db).latest_monitoring_for(
        [deployment.id for deployment in deployments]
    )
    deployment_health = [
        DeploymentHealthItem(
            id=deployment.id,
            name=deployment.name,
            status=deployment.status,
            model_name=(
                deployment.registered_model.name if deployment.registered_model else "Unknown"
            ),
            model_version=deployment.model_version.version if deployment.model_version else 0,
            latest_monitoring_status=(
                latest_monitoring[deployment.id].status
                if deployment.id in latest_monitoring
                else None
            ),
            last_request_at=deployment.last_request_at,
            created_at=deployment.created_at,
        )
        for deployment in deployments[:10]
    ]
    status_counts: dict[str, int] = defaultdict(int)
    for deployment in deployments:
        status_counts[deployment.status] += 1

    recent_jobs = [
        RecentJobItem(
            id=job.id,
            name=job.name,
            status=job.status,
            progress=job.progress,
            problem_type=job.problem_type,
            created_at=job.created_at,
        )
        for job in db.execute(
            select(TrainingJob)
            .where(TrainingJob.project_id == project.id)
            .order_by(TrainingJob.created_at.desc())
            .limit(6)
        )
        .scalars()
        .all()
    ]

    recent_events = [
        RecentEventItem(
            id=event.id,
            action=event.action,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            details=event.details,
            created_at=event.created_at,
        )
        for event in AuditRepository(db).list_for_project(project.id, 0, 8)
    ]

    models = list(
        db.execute(
            select(RegisteredModel)
            .options(selectinload(RegisteredModel.versions))
            .where(RegisteredModel.project_id == project.id)
            .order_by(RegisteredModel.updated_at.desc())
            .limit(6)
        )
        .scalars()
        .all()
    )
    latest_models: list[LatestModelItem] = []
    for model in models:
        versions = sorted(model.versions, key=lambda item: item.version, reverse=True)
        if not versions:
            continue
        latest = versions[0]
        latest_models.append(
            LatestModelItem(
                id=model.id,
                name=model.name,
                version=latest.version,
                stage=latest.stage,
                algorithm=latest.algorithm,
                metrics=latest.metrics,
                created_at=latest.created_at,
            )
        )

    primary = None
    if completed_experiments:
        primary = primary_metric(completed_experiments[0].problem_type)

    return OverviewResponse(
        counts=counts,
        training_activity=training_activity,
        experiment_performance=performance_points,
        model_performance=model_performance,
        deployment_health=deployment_health,
        deployment_status_counts=dict(status_counts),
        recent_jobs=recent_jobs,
        recent_events=recent_events,
        latest_models=latest_models,
        primary_metric=primary,
    )
