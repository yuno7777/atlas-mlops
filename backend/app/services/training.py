from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.logging import request_id_ctx
from app.ml.algorithms import get_algorithm, validate_hyperparameters
from app.ml.evaluation import metric_directions
from app.ml.utils import float_or_none
from app.models.dataset import DatasetVersion
from app.models.enums import JobStatus, ProblemType
from app.models.training import Experiment, TrainingDispatch, TrainingJob, TrainingJobLog
from app.models.user import User
from app.repositories.datasets import DatasetRepository
from app.repositories.training import ExperimentRepository, TrainingRepository
from app.schemas.experiment import (
    BestMetric,
    ExperimentCompareResponse,
    ExperimentDetail,
    ExperimentSummary,
)
from app.schemas.training import (
    TrainingExecutionPolicy,
    TrainingJobCreateRequest,
    TrainingJobDetail,
    TrainingJobLogOut,
    TrainingJobLogsResponse,
    TrainingJobSummary,
)
from app.services.access import require_project
from app.services.audit import record_audit
from app.workers.dispatch import dispatch_training_job


def _job_duration(job: TrainingJob) -> float | None:
    if job.started_at is None:
        return None
    end = job.completed_at or datetime.now(UTC)
    start = job.started_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    return max(0.0, (end - start).total_seconds())


def _job_summary(job: TrainingJob, dataset: DatasetVersion | None = None) -> TrainingJobSummary:
    version = dataset or job.dataset_version
    return TrainingJobSummary(
        id=job.id,
        project_id=job.project_id,
        name=job.name,
        problem_type=job.problem_type,
        status=job.status,
        progress=job.progress,
        status_message=job.status_message,
        dataset_version_id=job.dataset_version_id,
        dataset_name=version.dataset.name if version and version.dataset else "Unknown dataset",
        dataset_version=version.version if version else 0,
        target_column=job.target_column,
        algorithm_count=len(job.algorithms or []),
        retrain_source_deployment_id=job.retrain_source_deployment_id,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_seconds=_job_duration(job),
    )


def experiment_summary(
    experiment: Experiment,
    *,
    dataset_name: str | None = None,
    dataset_version: int | None = None,
    registration=None,
) -> ExperimentSummary:
    version = experiment.dataset_version
    if version is not None:
        dataset_name = dataset_name or (version.dataset.name if version.dataset else None)
        dataset_version = dataset_version or version.version
    return ExperimentSummary(
        id=experiment.id,
        project_id=experiment.project_id,
        training_job_id=experiment.training_job_id,
        dataset_version_id=experiment.dataset_version_id,
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        name=experiment.name,
        algorithm=experiment.algorithm,
        algorithm_label=experiment.algorithm_label,
        problem_type=experiment.problem_type,
        params=experiment.params,
        metrics=experiment.metrics,
        cv_metrics=experiment.cv_metrics,
        status=experiment.status,
        error_message=experiment.error_message,
        mlflow_run_id=experiment.mlflow_run_id,
        tracking_warning=experiment.tracking_warning,
        training_duration_seconds=experiment.training_duration_seconds,
        created_at=experiment.created_at,
        started_at=experiment.started_at,
        completed_at=experiment.completed_at,
        registered_model_id=registration.registered_model_id if registration else None,
        registered_model_name=(
            registration.registered_model.name
            if registration and registration.registered_model
            else None
        ),
        registered_version=registration.version if registration else None,
        registered_stage=registration.stage if registration else None,
        artifact_available=bool(experiment.artifact_key),
    )


def _find_replay(
    db: Session, user: User, project_id: str, key: str, fingerprint: str
) -> TrainingJobDetail | None:
    job = db.scalar(
        select(TrainingJob).where(
            TrainingJob.project_id == project_id,
            TrainingJob.created_by == user.id,
            TrainingJob.idempotency_key == key,
        )
    )
    if job is None:
        return None
    if job.config.get("submission_sha256") != fingerprint:
        raise ConflictError(
            "This Idempotency-Key was already used for a different training request."
        )
    return get_training_job(db, user, job.id)


def create_training_job(
    db: Session,
    user: User,
    payload: TrainingJobCreateRequest,
    ip_address: str | None = None,
    *,
    retrain_source_deployment_id: str | None = None,
    idempotency_key: str | None = None,
) -> TrainingJobDetail:
    project, _role = require_project(db, user, payload.project_id, write=True)
    fingerprint = ""
    if idempotency_key is not None:
        request_data = payload.model_dump(mode="json")
        if payload.execution_policy is None:
            request_data.pop("execution_policy")
        canonical = json.dumps(request_data, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
        replay = _find_replay(db, user, project.id, idempotency_key, fingerprint)
        if replay is not None:
            return replay
    dataset_repository = DatasetRepository(db)
    dataset_version = dataset_repository.get_version(payload.dataset_version_id)
    if dataset_version is None or dataset_version.dataset.project_id != project.id:
        raise NotFoundError("Dataset version not found.")
    if dataset_version.status != "ready":
        raise ConflictError("The dataset version is not ready for training.")
    schema_columns = [column["name"] for column in dataset_version.schema_json]
    problem_type = payload.problem_type

    target = payload.target_column
    if problem_type in {ProblemType.CLASSIFICATION, ProblemType.REGRESSION} and not target:
        raise ValidationError("A target column is required for supervised training.")
    if target and target not in schema_columns:
        raise ValidationError(f"Target column '{target}' is not in the dataset.")
    sensitive_columns = payload.sensitive_columns
    missing_sensitive = [column for column in sensitive_columns if column not in schema_columns]
    if missing_sensitive:
        raise ValidationError(
            f"Unknown sensitive audit columns: {', '.join(missing_sensitive[:10])}"
        )
    if target and target in sensitive_columns:
        raise ValidationError("The target column cannot also be a sensitive audit column.")
    features = payload.feature_columns
    if features:
        missing = [column for column in features if column not in schema_columns]
        if missing:
            raise ValidationError(f"Unknown feature columns: {', '.join(missing[:10])}")
        if target and target in features:
            raise ValidationError("The target column cannot also be a feature.")
        overlap = sorted(set(features) & set(sensitive_columns))
        if overlap:
            raise ValidationError(
                "Sensitive audit columns must be excluded from model features: "
                + ", ".join(overlap[:10])
            )
    else:
        available = [
            column
            for column in schema_columns
            if column != target and column not in sensitive_columns
        ]
        if len(available) < 2:
            raise ValidationError(
                "At least two feature columns are required after excluding the target."
            )
    if features and len(features) < 2:
        raise ValidationError("At least two feature columns are required.")
    if problem_type == ProblemType.CLUSTERING and target and target in (features or []):
        raise ValidationError("The target column cannot also be a feature.")

    algorithm_ids = [selection.algorithm for selection in payload.algorithms]
    if len(set(algorithm_ids)) != len(algorithm_ids):
        raise ValidationError("Each algorithm may only be selected once per job.")
    normalized_algorithms = []
    for selection in payload.algorithms:
        spec = get_algorithm(selection.algorithm, problem_type)
        values = validate_hyperparameters(spec, selection.hyperparameters)
        normalized_algorithms.append({"algorithm": spec.id, "hyperparameters": values})

    if problem_type == ProblemType.CLUSTERING and payload.cv_folds:
        raise ValidationError("Cross-validation is not supported for clustering jobs.")

    job_name = payload.name or (
        f"{dataset_version.dataset.name} · {problem_type} · "
        f"{datetime.now(UTC).strftime('%b %d, %H:%M')}"
    )
    execution_policy = (payload.execution_policy or TrainingExecutionPolicy()).model_dump()
    if execution_policy["max_attempts"] is None:
        execution_policy["max_attempts"] = get_settings().training_max_attempts
    config = {
        "execution_policy": execution_policy,
        "test_size": payload.test_size,
        "random_seed": payload.random_seed,
        "cv_folds": payload.cv_folds,
        "register_model_name": payload.register_model_name,
        "sensitive_columns": sensitive_columns,
        "request_id": request_id_ctx.get(),
    }
    if idempotency_key is not None:
        config["submission_sha256"] = fingerprint
    if payload.workflow_run_id:
        from app.models.modelops import WorkflowRun

        workflow_run = db.get(WorkflowRun, payload.workflow_run_id)
        if (
            workflow_run is None
            or workflow_run.project_id != project.id
            or workflow_run.created_by != user.id
            or workflow_run.status not in {"queued", "scheduled"}
        ):
            raise ValidationError("The workflow run is unavailable for this training job.")
        config["workflow_run_id"] = workflow_run.id
    job = TrainingJob(
        project_id=project.id,
        dataset_version_id=dataset_version.id,
        name=job_name[:160],
        problem_type=problem_type,
        target_column=target,
        feature_columns=payload.feature_columns,
        algorithms=normalized_algorithms,
        config=config,
        idempotency_key=idempotency_key,
        status=JobStatus.QUEUED,
        progress=0,
        status_message="Queued",
        created_by=user.id,
        retrain_source_deployment_id=retrain_source_deployment_id,
    )
    db.add(job)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        if idempotency_key is not None:
            replay = _find_replay(db, user, payload.project_id, idempotency_key, fingerprint)
            if replay is not None:
                return replay
        raise
    db.add(TrainingDispatch(job_id=job.id))
    if payload.workflow_run_id:
        workflow_run.training_job_id = job.id
        workflow_run.status = "queued"
        workflow_run.scheduled_at = None
        workflow_run.updated_at = datetime.now(UTC)
    db.add(
        TrainingJobLog(
            job_id=job.id,
            level="info",
            message=f"Queued {len(normalized_algorithms)} algorithm run(s) for dataset version {dataset_version.version}.",
        )
    )
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="training_job.created",
        resource_type="training_job",
        resource_id=job.id,
        details={
            "algorithms": algorithm_ids,
            "problem_type": problem_type,
            "dataset_version_id": dataset_version.id,
            "retrain_source_deployment_id": retrain_source_deployment_id,
        },
        ip_address=ip_address,
    )
    db.commit()

    dispatch_training_job(job.id)

    db.expire_all()
    return get_training_job(db, user, job.id)


def get_training_job(db: Session, user: User, job_id: str) -> TrainingJobDetail:
    repository = TrainingRepository(db)
    job = repository.get_job_detail(job_id)
    if job is None:
        raise NotFoundError("Training job not found.")
    require_project(db, user, job.project_id)
    dataset = job.dataset_version
    dataset_name = dataset.dataset.name if dataset and dataset.dataset else None
    registrations = ExperimentRepository(db).registrations_for(
        [experiment.id for experiment in job.experiments]
    )
    experiments = [
        experiment_summary(
            experiment,
            dataset_name=dataset_name,
            dataset_version=dataset.version if dataset else None,
            registration=registrations.get(experiment.id),
        )
        for experiment in sorted(job.experiments, key=lambda item: item.created_at)
    ]
    return TrainingJobDetail(
        **_job_summary(job).model_dump(),
        feature_columns=job.feature_columns,
        algorithms=job.algorithms,
        config=job.config,
        error_message=job.error_message,
        cancel_requested=job.cancel_requested,
        execution_attempt=job.execution_attempt,
        execution_deadline_at=job.execution_deadline_at,
        cancel_deadline_at=job.cancel_deadline_at,
        experiments=experiments,
        created_by=job.created_by,
    )


def list_training_jobs(
    db: Session,
    user: User,
    *,
    project_id: str,
    status: str | None,
    search: str | None,
    page: int,
    page_size: int,
) -> tuple[list[TrainingJobSummary], int]:
    require_project(db, user, project_id)
    repository = TrainingRepository(db)
    jobs, total = repository.list_jobs(
        project_id, status, search, (page - 1) * page_size, page_size
    )
    return [_job_summary(job) for job in jobs], total


def get_training_logs(
    db: Session, user: User, job_id: str, after_id: int | None, limit: int
) -> TrainingJobLogsResponse:
    repository = TrainingRepository(db)
    job = repository.get_job(job_id)
    if job is None:
        raise NotFoundError("Training job not found.")
    require_project(db, user, job.project_id)
    logs = repository.logs(job_id, after_id, limit)
    items = [
        TrainingJobLogOut(
            id=log.id, level=log.level, message=log.message, created_at=log.created_at
        )
        for log in logs
    ]
    return TrainingJobLogsResponse(items=items, last_id=items[-1].id if items else None)


def cancel_training_job(
    db: Session, user: User, job_id: str, ip_address: str | None = None
) -> TrainingJobDetail:
    repository = TrainingRepository(db)
    job = repository.get_job(job_id)
    if job is None:
        raise NotFoundError("Training job not found.")
    project, _role = require_project(db, user, job.project_id, write=True)
    policy = TrainingExecutionPolicy.model_validate(job.config.get("execution_policy", {}))
    now = datetime.now(UTC)
    if not repository.request_cancellation(
        job.id, now, now + timedelta(seconds=policy.cancel_grace_seconds)
    ):
        raise ConflictError("This job has already finished.")
    db.add(
        TrainingJobLog(
            job_id=job.id,
            level="warning",
            message="Cancellation requested by user.",
        )
    )
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="training_job.cancelled",
        resource_type="training_job",
        resource_id=job.id,
        ip_address=ip_address,
    )
    db.commit()
    return get_training_job(db, user, job_id)


def list_experiments(
    db: Session,
    user: User,
    *,
    project_id: str,
    dataset_version_id: str | None,
    algorithm: str | None,
    status: str | None,
    problem_type: str | None,
    job_id: str | None,
    search: str | None,
    sort: str,
    page: int,
    page_size: int,
) -> tuple[list[ExperimentSummary], int]:
    require_project(db, user, project_id)
    repository = ExperimentRepository(db)
    experiments, total = repository.list(
        project_id,
        dataset_version_id,
        algorithm,
        status,
        problem_type,
        job_id,
        search,
        sort,
        (page - 1) * page_size,
        page_size,
    )
    registrations = repository.registrations_for([experiment.id for experiment in experiments])
    return [
        experiment_summary(experiment, registration=registrations.get(experiment.id))
        for experiment in experiments
    ], total


def get_experiment(db: Session, user: User, experiment_id: str) -> ExperimentDetail:
    repository = ExperimentRepository(db)
    experiment = repository.get(experiment_id)
    if experiment is None:
        raise NotFoundError("Experiment not found.")
    require_project(db, user, experiment.project_id)
    registrations = repository.registrations_for([experiment.id])
    base = experiment_summary(experiment, registration=registrations.get(experiment.id))
    return ExperimentDetail(
        **base.model_dump(),
        reference_profile=experiment.reference_profile,
        job_name=experiment.job.name if experiment.job else None,
    )


def compare_experiments(
    db: Session, user: User, experiment_ids: list[str]
) -> ExperimentCompareResponse:
    repository = ExperimentRepository(db)
    experiments = repository.by_ids(experiment_ids)
    if len(experiments) != len(set(experiment_ids)):
        raise NotFoundError("One or more experiments were not found.")
    project_ids = {experiment.project_id for experiment in experiments}
    if len(project_ids) != 1:
        raise ValidationError("Experiments must belong to the same project to compare.")
    require_project(db, user, experiments[0].project_id)
    problem_types = {experiment.problem_type for experiment in experiments}
    if len(problem_types) != 1:
        raise ValidationError("Only experiments with the same problem type can be compared.")
    by_id = {experiment.id: experiment for experiment in experiments}
    ordered = [by_id[experiment_id] for experiment_id in experiment_ids]
    registrations = repository.registrations_for(experiment_ids)
    summaries = [
        experiment_summary(experiment, registration=registrations.get(experiment.id))
        for experiment in ordered
    ]
    problem_type = ordered[0].problem_type
    expected_metrics = list(metric_directions(problem_type).keys())
    metric_keys = [
        metric
        for metric in expected_metrics
        if any(
            isinstance(experiment.metrics.get(metric), (int, float))
            and not isinstance(experiment.metrics.get(metric), bool)
            for experiment in ordered
        )
    ]
    directions = metric_directions(problem_type)
    best: dict[str, BestMetric] = {}
    for metric in metric_keys:
        candidates: list[tuple[str, float]] = []
        for experiment in ordered:
            value = float_or_none(experiment.metrics.get(metric))
            if value is not None and math.isfinite(value):
                candidates.append((experiment.id, value))
        if not candidates:
            continue
        if directions[metric] == "max":
            winner = max(candidates, key=lambda item: item[1])
        else:
            winner = min(candidates, key=lambda item: item[1])
        best[metric] = BestMetric(
            experiment_id=winner[0], value=winner[1], direction=directions[metric]
        )
    return ExperimentCompareResponse(
        problem_type=problem_type,
        metric_keys=metric_keys,
        directions={key: directions[key] for key in metric_keys},
        best=best,
        experiments=summaries,
    )
