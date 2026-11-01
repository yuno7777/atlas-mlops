from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.db.session import SessionLocal
from app.ml.evaluation import primary_metric
from app.models.dataset import DatasetVersion
from app.models.modelops import WorkflowRun
from app.models.training import TrainingJob
from app.models.user import User
from app.schemas.modelops import BenchmarkReportResponse, PipelineRunCreate, PipelineRunResponse
from app.schemas.training import TrainingJobCreateRequest
from app.services.access import require_project
from app.services.audit import record_audit
from app.services.training import create_training_job, experiment_summary

logger = logging.getLogger(__name__)

_STEPS = [
    {"id": "validate", "name": "Validate data", "depends_on": []},
    {"id": "prepare", "name": "Split and preprocess", "depends_on": ["validate"]},
    {"id": "train", "name": "Train models", "depends_on": ["prepare"]},
    {"id": "evaluate", "name": "Evaluate and compare", "depends_on": ["train"]},
    {"id": "fairness", "name": "Fairness audit", "depends_on": ["evaluate"], "optional": True},
    {"id": "register", "name": "Register best model", "depends_on": ["evaluate"], "optional": True},
]

_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "classification_baselines",
        "name": "Tabular classification baselines",
        "problem_type": "classification",
        "summary": "Compare linear, bagged-tree, and boosted-tree classifiers on one fixed holdout and stratified CV folds.",
        "metric_keys": ["accuracy", "f1_weighted", "roc_auc"],
        "algorithms": [
            {"algorithm": "logistic_regression", "hyperparameters": {}},
            {"algorithm": "random_forest_classifier", "hyperparameters": {"n_estimators": 200}},
            {"algorithm": "gradient_boosting_classifier", "hyperparameters": {"n_estimators": 150}},
        ],
        "protocol": {
            "test_size": 0.2,
            "random_seed": 42,
            "cv_folds": 3,
            "split": "stratified holdout; stratified cross-validation on training rows",
        },
    },
    {
        "id": "classification_imbalanced",
        "name": "Imbalanced classification",
        "problem_type": "classification",
        "summary": "Compare a class-weighted linear model with tree ensembles; inspect weighted F1 and ROC AUC alongside accuracy.",
        "metric_keys": ["f1_weighted", "roc_auc", "accuracy"],
        "algorithms": [
            {"algorithm": "logistic_regression", "hyperparameters": {"class_weight": "balanced"}},
            {"algorithm": "random_forest_classifier", "hyperparameters": {"n_estimators": 200}},
            {"algorithm": "gradient_boosting_classifier", "hyperparameters": {"n_estimators": 150}},
        ],
        "protocol": {
            "test_size": 0.2,
            "random_seed": 42,
            "cv_folds": 3,
            "split": "stratified holdout; stratified cross-validation on training rows",
        },
    },
    {
        "id": "regression_baselines",
        "name": "Tabular regression baselines",
        "problem_type": "regression",
        "summary": "Compare least-squares, regularized linear, random-forest, and boosted-tree regressors on a reproducible split.",
        "metric_keys": ["r2", "rmse", "mae"],
        "algorithms": [
            {"algorithm": "linear_regression", "hyperparameters": {}},
            {"algorithm": "ridge_regression", "hyperparameters": {"alpha": 1.0}},
            {"algorithm": "random_forest_regressor", "hyperparameters": {"n_estimators": 200}},
            {"algorithm": "gradient_boosting_regressor", "hyperparameters": {"n_estimators": 150}},
        ],
        "protocol": {
            "test_size": 0.2,
            "random_seed": 42,
            "cv_folds": 3,
            "split": "random holdout; shuffled K-fold cross-validation on training rows",
        },
    },
    {
        "id": "small_data_regression",
        "name": "Small-data regression",
        "problem_type": "regression",
        "summary": "A compact linear and tree comparison with the same holdout and CV protocol for small tabular datasets.",
        "metric_keys": ["r2", "rmse", "mae"],
        "algorithms": [
            {"algorithm": "ridge_regression", "hyperparameters": {"alpha": 1.0}},
            {
                "algorithm": "random_forest_regressor",
                "hyperparameters": {"n_estimators": 100, "max_depth": 8},
            },
            {"algorithm": "gradient_boosting_regressor", "hyperparameters": {"n_estimators": 100}},
        ],
        "protocol": {
            "test_size": 0.2,
            "random_seed": 42,
            "cv_folds": 3,
            "split": "random holdout; shuffled K-fold cross-validation on training rows",
        },
    },
    {
        "id": "clustering_baseline",
        "name": "Clustering baseline",
        "problem_type": "clustering",
        "summary": "Evaluate K-Means with silhouette, Davies–Bouldin, and Calinski–Harabasz scores; no target column is used.",
        "metric_keys": ["silhouette", "davies_bouldin", "calinski_harabasz"],
        "algorithms": [{"algorithm": "kmeans", "hyperparameters": {"n_clusters": 4, "n_init": 10}}],
        "protocol": {
            "test_size": 0.2,
            "random_seed": 42,
            "cv_folds": 0,
            "split": "random holdout; clustering cross-validation is not supported",
        },
    },
]


def pipeline_templates(problem_type: str | None = None) -> list[dict[str, Any]]:
    return [
        {**template, "steps": _STEPS}
        for template in _TEMPLATES
        if problem_type is None or template["problem_type"] == problem_type
    ]


def _template(template_id: str) -> dict[str, Any]:
    for item in _TEMPLATES:
        if item["id"] == template_id:
            return item
    raise NotFoundError("Pipeline template not found.")


def _step_states(template: dict[str, Any]) -> list[dict[str, Any]]:
    return [{**step, "status": "queued", "detail": "Waiting for dependencies."} for step in _STEPS]


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _cache_key(dataset: DatasetVersion, template: dict[str, Any], config: dict[str, Any]) -> str:
    stable_config = {
        key: value
        for key, value in config.items()
        if key not in {"scheduled_at", "cache_enabled", "max_attempts", "name"}
    }
    value = json.dumps(
        {"dataset_checksum": dataset.checksum, "template": template["id"], "config": stable_config},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _training_request(run: WorkflowRun) -> TrainingJobCreateRequest:
    config = dict(run.config)
    return TrainingJobCreateRequest(
        **config,
        project_id=run.project_id,
        dataset_version_id=run.dataset_version_id,
        workflow_run_id=run.id,
    )


def _enqueue(db: Session, run: WorkflowRun, user: User, ip_address: str | None = None) -> None:
    if run.training_job_id:
        return
    try:
        create_training_job(db, user, _training_request(run), ip_address)
        db.refresh(run)
    except Exception as exc:
        db.rollback()
        failed = db.get(WorkflowRun, run.id)
        if failed is not None:
            failed.status = "failed"
            failed.error_message = str(exc).splitlines()[0][:500]
            failed.completed_at = datetime.now(UTC)
            db.add(failed)
            db.commit()
        raise


def create_pipeline_run(
    db: Session,
    user: User,
    payload: PipelineRunCreate,
    ip_address: str | None = None,
    *,
    parent_run_id: str | None = None,
    attempt: int = 1,
) -> PipelineRunResponse:
    project, _ = require_project(db, user, payload.project_id, write=True)
    template = _template(payload.template_id)
    dataset = db.get(DatasetVersion, payload.dataset_version_id)
    if dataset is None or dataset.dataset.project_id != project.id:
        raise NotFoundError("Dataset version not found.")
    if dataset.status != "ready":
        raise ConflictError("The dataset version is not ready for pipeline runs.")
    if payload.sensitive_columns and template["problem_type"] == "clustering":
        raise ValidationError(
            "Fairness audits require a supervised classification or regression pipeline."
        )
    if payload.cv_folds < 2 and template["problem_type"] != "clustering":
        raise ValidationError("Supervised benchmarks require at least two cross-validation folds.")
    run_config = {
        "target_column": payload.target_column,
        "feature_columns": payload.feature_columns,
        "sensitive_columns": payload.sensitive_columns,
        "algorithms": template["algorithms"],
        "problem_type": template["problem_type"],
        "test_size": payload.test_size,
        "random_seed": payload.random_seed,
        "cv_folds": 0 if template["problem_type"] == "clustering" else payload.cv_folds,
        "register_model_name": payload.register_model_name,
        "name": payload.name or template["name"],
        "cache_enabled": payload.cache_enabled,
        "max_attempts": payload.max_attempts,
    }
    key = _cache_key(dataset, template, run_config)
    run = WorkflowRun(
        project_id=project.id,
        dataset_version_id=dataset.id,
        parent_run_id=parent_run_id,
        template_id=template["id"],
        name=run_config["name"][:160],
        status="queued",
        step_states=_step_states(template),
        config=run_config,
        cache_key=key,
        cache_hit=False,
        attempt=attempt,
        max_attempts=payload.max_attempts,
        scheduled_at=_normalize_datetime(payload.scheduled_at),
        created_by=user.id,
    )
    if run.scheduled_at and run.scheduled_at <= datetime.now(UTC):
        raise ValidationError("scheduled_at must be in the future.")
    if run.scheduled_at:
        run.status = "scheduled"
    db.add(run)
    db.flush()

    if payload.cache_enabled and not run.scheduled_at:
        cached = db.execute(
            select(WorkflowRun)
            .where(
                WorkflowRun.project_id == project.id,
                WorkflowRun.cache_key == key,
                WorkflowRun.status == "completed",
                WorkflowRun.training_job_id.is_not(None),
            )
            .order_by(WorkflowRun.completed_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if cached is not None:
            run.status = "completed"
            run.training_job_id = cached.training_job_id
            run.cache_hit = True
            run.completed_at = datetime.now(UTC)
            run.step_states = [
                {**step, "status": "completed", "detail": "Reused an identical successful run."}
                for step in _step_states(template)
            ]
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="workflow_run.created",
        resource_type="workflow_run",
        resource_id=run.id,
        details={"template_id": run.template_id, "status": run.status, "cache_key": key},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(run)
    if run.status == "queued":
        _enqueue(db, run, user, ip_address)
        db.refresh(run)
    return pipeline_run_out(db, run)


def pipeline_run_out(db: Session, run: WorkflowRun) -> PipelineRunResponse:
    job = db.get(TrainingJob, run.training_job_id) if run.training_job_id else None
    experiments = []
    if job:
        for experiment in job.experiments:
            experiments.append(experiment_summary(experiment).model_dump(mode="json"))
    status = run.status
    if job and status not in {"completed", "failed", "cancelled", "scheduled"}:
        status = job.status
    return PipelineRunResponse(
        id=run.id,
        project_id=run.project_id,
        dataset_version_id=run.dataset_version_id,
        training_job_id=run.training_job_id,
        parent_run_id=run.parent_run_id,
        template_id=run.template_id,
        name=run.name,
        status=status,
        step_states=run.step_states,
        config=run.config,
        cache_hit=run.cache_hit,
        attempt=run.attempt,
        max_attempts=run.max_attempts,
        scheduled_at=run.scheduled_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error_message=run.error_message or (job.error_message if job else None),
        created_at=run.created_at,
        experiments=experiments,
    )


def list_pipeline_runs(
    db: Session, user: User, project_id: str, limit: int = 50
) -> list[PipelineRunResponse]:
    require_project(db, user, project_id)
    runs = list(
        db.execute(
            select(WorkflowRun)
            .where(WorkflowRun.project_id == project_id)
            .order_by(WorkflowRun.created_at.desc())
            .limit(limit)
        ).scalars()
    )
    return [pipeline_run_out(db, run) for run in runs]


def get_pipeline_run(db: Session, user: User, run_id: str) -> PipelineRunResponse:
    run = db.get(WorkflowRun, run_id)
    if run is None:
        raise NotFoundError("Workflow run not found.")
    require_project(db, user, run.project_id)
    return pipeline_run_out(db, run)


def retry_pipeline_run(
    db: Session, user: User, run_id: str, ip_address: str | None = None
) -> PipelineRunResponse:
    old = db.get(WorkflowRun, run_id)
    if old is None:
        raise NotFoundError("Workflow run not found.")
    require_project(db, user, old.project_id, write=True)
    if old.status != "failed":
        raise ConflictError("Only failed workflow runs can be retried.")
    if old.attempt >= old.max_attempts:
        raise ConflictError("This workflow run has reached its retry limit.")
    values = dict(old.config)
    cache_enabled = bool(values.pop("cache_enabled", True))
    max_attempts = int(values.pop("max_attempts", old.max_attempts))
    payload = PipelineRunCreate(
        project_id=old.project_id,
        dataset_version_id=old.dataset_version_id,
        template_id=old.template_id,
        cache_enabled=cache_enabled,
        max_attempts=max_attempts,
        **values,
    )
    return create_pipeline_run(
        db,
        user,
        payload,
        ip_address,
        parent_run_id=old.id,
        attempt=old.attempt + 1,
    )


def process_due_pipeline_runs(limit: int = 20) -> int:
    db = SessionLocal()
    processed = 0
    try:
        due = list(
            db.execute(
                select(WorkflowRun)
                .where(
                    WorkflowRun.status == "scheduled",
                    WorkflowRun.scheduled_at <= datetime.now(UTC),
                )
                .order_by(WorkflowRun.scheduled_at.asc())
                .limit(limit)
            ).scalars()
        )
        for run in due:
            user = db.get(User, run.created_by)
            if user is None or not user.is_active:
                run.status = "failed"
                run.error_message = "Workflow owner is no longer active."
                run.completed_at = datetime.now(UTC)
                db.add(run)
                db.commit()
                continue
            run.status = "queued"
            db.add(run)
            db.commit()
            try:
                _enqueue(db, run, user)
                processed += 1
            except Exception:
                logger.exception(
                    "Scheduled workflow could not be enqueued", extra={"run_id": run.id}
                )
        return processed
    finally:
        db.close()


def benchmark_reports(
    db: Session, user: User, project_id: str, limit: int = 40
) -> list[BenchmarkReportResponse]:
    require_project(db, user, project_id)
    jobs = list(
        db.execute(
            select(TrainingJob)
            .where(TrainingJob.project_id == project_id)
            .order_by(TrainingJob.created_at.desc())
            .limit(limit)
        ).scalars()
    )
    reports: list[BenchmarkReportResponse] = []
    for job in jobs:
        dataset = job.dataset_version
        if dataset is None or dataset.dataset is None:
            continue
        experiments = [
            experiment for experiment in job.experiments if experiment.status == "completed"
        ]
        if len(experiments) < 2:
            continue
        metric = primary_metric(job.problem_type)
        direction = "min" if metric in {"rmse", "mae", "davies_bouldin"} else "max"

        def score(experiment, metric=metric, direction=direction):
            value = experiment.metrics.get(metric)
            if isinstance(value, (int, float)):
                return float(value)
            return float("inf") if direction == "min" else float("-inf")

        experiments.sort(key=score, reverse=direction == "max")
        reports.append(
            BenchmarkReportResponse(
                training_job_id=job.id,
                name=job.name,
                dataset_name=dataset.dataset.name,
                dataset_version=dataset.version,
                dataset_version_id=dataset.id,
                problem_type=job.problem_type,
                status=job.status,
                protocol={
                    "test_size": job.config.get("test_size", 0.2),
                    "random_seed": job.config.get("random_seed", 42),
                    "cv_folds": job.config.get("cv_folds", 0),
                    "primary_metric": metric,
                    "comparison_count": len(experiments),
                },
                experiments=[
                    {
                        "id": experiment.id,
                        "name": experiment.name,
                        "algorithm": experiment.algorithm,
                        "algorithm_label": experiment.algorithm_label,
                        "metrics": experiment.metrics,
                        "cv_metrics": experiment.cv_metrics,
                        "training_duration_seconds": experiment.training_duration_seconds,
                        "created_at": experiment.created_at,
                    }
                    for experiment in experiments
                ],
                created_at=job.created_at,
            )
        )
    return reports
