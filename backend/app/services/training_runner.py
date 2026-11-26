from __future__ import annotations

import hashlib
import json
import logging
import math
import platform
import tempfile
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from pathlib import Path
from typing import Any

import joblib
from botocore.exceptions import ConnectionError as StorageConnectionError
from botocore.exceptions import ReadTimeoutError
from sklearn.pipeline import Pipeline
from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import TrainingError
from app.core.logging import request_id_ctx, run_id_ctx
from app.core.metrics import ACTIVE_TRAINING_JOBS, EXPERIMENTS, TRAINING_JOBS
from app.db.session import SessionLocal
from app.ml.algorithms import get_algorithm
from app.ml.evaluation import METRIC_DIRECTIONS, primary_metric
from app.ml.tracking import MLflowTracker, format_tracking_tags
from app.ml.training import TrainingConfig, train_algorithm
from app.ml.utils import float_or_none
from app.ml.validation import read_dataframe
from app.models.enums import ExperimentStatus, JobStatus
from app.models.modelops import WorkflowRun
from app.models.training import Experiment, TrainingDispatch, TrainingJob, TrainingJobLog
from app.repositories.training import TrainingRepository
from app.schemas.training import TrainingExecutionPolicy
from app.services.storage import (
    ArtifactIntegrityError,
    copy_verified,
    get_storage,
    training_artifact_prefix,
)
from app.workers.training_lease import LeaseLost, TrainingLease

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


def _log(db: Session, job: TrainingJob, message: str, level: str = "info") -> None:
    db.add(TrainingJobLog(job_id=job.id, level=level, message=message[:4000]))


def _progress(db: Session, job: TrainingJob, value: int, message: str | None = None) -> None:
    job.progress = max(0, min(100, value))
    if message:
        job.status_message = message[:255]
    db.add(job)


def _record_tracking_failure(db: Session, job: TrainingJob, message: str) -> None:
    db.add(TrainingJobLog(job_id=job.id, level="warning", message=message))


def _resolve_best(experiments: list[Experiment], problem_type: str) -> Experiment | None:
    completed = [
        experiment for experiment in experiments if experiment.status == ExperimentStatus.COMPLETED
    ]
    if not completed:
        return None
    metric = primary_metric(problem_type)
    direction = METRIC_DIRECTIONS.get(metric, "max")
    scored = [
        (experiment, float_or_none(experiment.metrics.get(metric))) for experiment in completed
    ]
    scored = [(experiment, value) for experiment, value in scored if value is not None]
    if not scored:
        return completed[0]
    if direction == "max":
        return max(scored, key=lambda item: item[1])[0]
    return min(scored, key=lambda item: item[1])[0]


def _persist_artifacts(
    job: TrainingJob,
    experiment: Experiment,
    pipeline: Pipeline,
    reference_profile: dict[str, Any],
    directory: Path,
) -> tuple[str, list[Path]]:
    storage = get_storage()
    prefix = training_artifact_prefix(job.id, experiment.id)
    model_path = directory / "model.joblib"
    reference_path = directory / "reference_profile.json"
    joblib.dump(pipeline, model_path)
    with model_path.open("rb") as model_file:
        reference_profile["provenance"]["model_sha256"] = hashlib.file_digest(
            model_file, "sha256"
        ).hexdigest()
    reference_path.write_text(json.dumps(reference_profile, indent=2), encoding="utf-8")
    model_key = f"{prefix}/model.joblib"
    storage.put_file(model_key, model_path)
    storage.put_file(f"{prefix}/reference_profile.json", reference_path)
    return model_key, [model_path, reference_path]


def _mark_job_failed(db: Session, job: TrainingJob, message: str) -> None:
    job.status = JobStatus.FAILED
    job.error_message = message[:4000]
    job.completed_at = _now()
    job.status_message = "Failed"
    _log(db, job, message, level="error")
    db.add(job)


def _workflow_steps(db: Session, job: TrainingJob, updates: dict[str, tuple[str, str]]) -> None:
    workflow_id = (job.config or {}).get("workflow_run_id")
    if not workflow_id:
        return
    run = db.get(WorkflowRun, workflow_id)
    if run is None:
        return
    states = [dict(step) for step in (run.step_states or [])]
    by_id = {step.get("id"): step for step in states}
    for step_id, (status, detail) in updates.items():
        step = by_id.get(step_id)
        if step is not None:
            step.update(status=status, detail=detail)
    run.step_states = states
    run.status = "running"
    run.started_at = run.started_at or _now()
    db.add(run)


def _finish_workflow(db: Session, job: TrainingJob) -> None:
    workflow_id = (job.config or {}).get("workflow_run_id")
    run = db.get(WorkflowRun, workflow_id) if workflow_id else None
    if run is None:
        return
    run.status = str(job.status)
    run.error_message = job.error_message
    run.completed_at = job.completed_at
    run.step_states = [
        {**step, "status": run.status} if step.get("status") in {"queued", "running"} else step
        for step in (run.step_states or [])
    ]


def _commit_terminal(db: Session, job: TrainingJob, lease: TrainingLease) -> None:
    _finish_workflow(db, job)
    job.execution_token = None
    job.lease_expires_at = None
    lease.commit(db)
    TRAINING_JOBS.labels(status=job.status).inc()


def execute_training_job(job_id: str) -> None:
    db = SessionLocal()
    job: TrainingJob | None = None
    lease = TrainingLease(job_id, get_settings().training_lease_seconds)
    claimed = False
    active = False
    run_token = run_id_ctx.set(job_id)
    request_token = request_id_ctx.set(None)
    try:
        repository = TrainingRepository(db)
        claimed = lease.claim(db)
        if not claimed:
            db.rollback()
            return
        job = repository.get_job_detail(job_id)
        if job is None:
            db.rollback()
            return
        request_id_ctx.set((job.config or {}).get("request_id"))
        ACTIVE_TRAINING_JOBS.inc()
        active = True
        logger.info("Training job claimed")
        _log(db, job, "Worker claimed the job; loading dataset.", level="info")
        _progress(db, job, 3, "Loading dataset")
        lease.commit(db)

        dataset_version = job.dataset_version
        storage = get_storage()
        with tempfile.TemporaryDirectory() as directory:
            dataset_path = Path(directory) / "dataset"
            try:
                with dataset_path.open("w+b") as snapshot:
                    copy_verified(
                        storage, dataset_version.storage_key, dataset_version.checksum, snapshot
                    )
                df = read_dataframe(dataset_path, dataset_version.original_filename)
            except ArtifactIntegrityError as exc:
                raise TrainingError("Dataset version failed its integrity check.") from exc
        provenance = {
            "dataset_version_id": dataset_version.id,
            "dataset_sha256": dataset_version.checksum,
            "code_revision": get_settings().code_revision,
            "python": platform.python_version(),
            "packages": {
                name: version(name)
                for name in ("scikit-learn", "numpy", "pandas", "scipy", "joblib", "pyarrow")
            },
        }
        _workflow_steps(
            db,
            job,
            {
                "validate": (
                    "completed",
                    f"Validated {len(df):,} rows and {len(df.columns)} columns.",
                ),
                "prepare": (
                    "running",
                    "Creating a reproducible holdout and preprocessing pipeline.",
                ),
            },
        )
        _log(
            db,
            job,
            f"Loaded dataset version {dataset_version.version} with {len(df):,} rows and {len(df.columns)} columns.",
        )
        _progress(db, job, 8, "Preparing experiments")
        lease.commit(db)

        training_config = TrainingConfig(
            problem_type=job.problem_type,
            target_column=job.target_column,
            feature_columns=job.feature_columns,
            test_size=float(job.config.get("test_size", 0.2)),
            random_seed=int(job.config.get("random_seed", 42)),
            cv_folds=int(job.config.get("cv_folds", 0)),
            sensitive_columns=list(job.config.get("sensitive_columns", [])),
        )
        completed_before_retry = {
            item.algorithm: item
            for item in job.experiments
            if item.status == ExperimentStatus.COMPLETED
        }
        experiments: list[Experiment] = []
        for selection in job.algorithms:
            if selection["algorithm"] in completed_before_retry:
                continue
            spec = get_algorithm(selection["algorithm"], job.problem_type)
            hyperparameters = selection.get("hyperparameters", {})
            experiment = Experiment(
                project_id=job.project_id,
                training_job_id=job.id,
                dataset_version_id=job.dataset_version_id,
                name=f"{job.name} · {spec.label}"[:200],
                algorithm=spec.id,
                algorithm_label=spec.label,
                problem_type=job.problem_type,
                params={
                    **hyperparameters,
                    "test_size": training_config.test_size,
                    "random_seed": training_config.random_seed,
                    "cv_folds": training_config.cv_folds,
                    "sensitive_columns": training_config.sensitive_columns,
                },
                metrics={},
                status=ExperimentStatus.QUEUED,
            )
            db.add(experiment)
            experiments.append(experiment)
        lease.commit(db)

        project_slug = job.project.slug if job.project else "project"
        tracker = MLflowTracker()
        total = len(experiments)
        successes = len(completed_before_retry)
        failures: list[str] = []

        for index, experiment in enumerate(experiments):
            db.refresh(job)
            if job.cancel_requested:
                break
            selection = next(
                item for item in job.algorithms if item["algorithm"] == experiment.algorithm
            )
            spec = get_algorithm(experiment.algorithm, job.problem_type)
            experiment.status = ExperimentStatus.RUNNING
            experiment.started_at = _now()
            _progress(
                db,
                job,
                10 + int((index / max(total, 1)) * 85),
                f"Training {spec.label} ({index + 1}/{total})",
            )
            _log(db, job, f"Fitting {spec.label}.")
            db.add(experiment)
            lease.commit(db)

            try:
                result = train_algorithm(
                    df,
                    spec,
                    selection.get("hyperparameters", {}),
                    training_config,
                )
                # Fitting may outlive the worker's lease. Check ownership before writing
                # attempt-specific files, then verify again before exposing their keys.
                lease.commit(db)
                for warning in result.warnings:
                    _record_tracking_failure(db, job, warning)
                result.reference_profile["provenance"] = provenance.copy()
                with tempfile.TemporaryDirectory() as temp_directory:
                    artifact_key, artifact_paths = _persist_artifacts(
                        job,
                        experiment,
                        result.pipeline,
                        result.reference_profile,
                        Path(temp_directory),
                    )
                    lease.commit(db)
                    run_id, tracking_warning = tracker.log_run(
                        experiment_name=f"atlas-{project_slug}",
                        run_name=experiment.name,
                        params=experiment.params,
                        metrics=result.metrics,
                        tags={
                            **format_tracking_tags(
                                job.id, job.project_id, job.dataset_version_id, job.problem_type
                            ),
                            "atlas.experiment_id": experiment.id,
                            "atlas.dataset_sha256": dataset_version.checksum,
                            "atlas.code_revision": provenance["code_revision"],
                        },
                        artifact_paths=artifact_paths,
                        model_pipeline=result.pipeline,
                    )
                if tracking_warning:
                    _record_tracking_failure(db, job, tracking_warning)

                experiment.status = ExperimentStatus.COMPLETED
                experiment.completed_at = _now()
                experiment.metrics = result.metrics
                experiment.cv_metrics = result.cv_metrics
                experiment.training_duration_seconds = round(result.duration_seconds, 3)
                experiment.artifact_key = artifact_key
                experiment.reference_profile = result.reference_profile
                experiment.mlflow_run_id = run_id
                experiment.tracking_warning = tracking_warning
                successes += 1
                _log(
                    db,
                    job,
                    f"{spec.label} completed in {result.duration_seconds:.1f}s. "
                    f"{_format_metrics(result.metrics)}",
                )
            except LeaseLost:
                raise
            except TrainingError as exc:
                if _is_retryable(exc):
                    raise
                message = str(exc)
                experiment.status = ExperimentStatus.FAILED
                experiment.error_message = message[:4000]
                experiment.completed_at = _now()
                failures.append(f"{spec.label}: {message}")
                _log(db, job, f"{spec.label} failed: {message}", level="error")
            except Exception as exc:  # unexpected algorithm error
                if _is_retryable(exc):
                    raise
                message = str(exc).splitlines()[0][:300] or exc.__class__.__name__
                experiment.status = ExperimentStatus.FAILED
                experiment.error_message = f"Unexpected training error: {message}"
                experiment.completed_at = _now()
                failures.append(f"{spec.label}: {message}")
                logger.exception("Unexpected training failure", extra={"job_id": job.id})
                _log(db, job, f"{spec.label} failed unexpectedly: {message}", level="error")
            db.add(experiment)
            _progress(
                db,
                job,
                10 + int(((index + 1) / max(total, 1)) * 85),
                f"Completed {index + 1}/{total} algorithm run(s)",
            )
            lease.commit(db)
            EXPERIMENTS.labels(status=experiment.status, algorithm=spec.id).inc()

        # Serialize final registration and cancellation with lease recovery.
        lease.guard(db)
        db.refresh(job)
        if job.cancel_requested:
            for experiment in experiments:
                if (
                    experiment.status == ExperimentStatus.QUEUED
                    or experiment.status == ExperimentStatus.RUNNING
                ):
                    experiment.status = ExperimentStatus.CANCELLED
                    experiment.completed_at = _now()
                    db.add(experiment)
            job.status = JobStatus.CANCELLED
            job.completed_at = _now()
            job.status_message = "Cancelled"
            job.progress = min(job.progress, 99)
            _log(db, job, "Job cancelled; remaining algorithms were skipped.", level="warning")
            db.add(job)
            _commit_terminal(db, job, lease)
            return

        completed_experiments = [*completed_before_retry.values()] + [
            experiment
            for experiment in experiments
            if experiment.status == ExperimentStatus.COMPLETED
        ]
        if not completed_experiments:
            _mark_job_failed(
                db,
                job,
                "All algorithm runs failed. " + ("; ".join(failures) if failures else ""),
            )
            _commit_terminal(db, job, lease)
            return

        _workflow_steps(
            db,
            job,
            {
                "prepare": ("completed", "Train/test split and preprocessing completed."),
                "train": ("completed", f"{len(completed_experiments)} model run(s) completed."),
                "evaluate": (
                    "completed",
                    "Held-out and configured cross-validation metrics recorded.",
                ),
                "fairness": (
                    "completed" if training_config.sensitive_columns else "skipped",
                    "Subgroup metrics recorded with audit columns excluded from model inputs."
                    if training_config.sensitive_columns
                    else "No sensitive audit columns were selected.",
                ),
                "register": (
                    "running",
                    "Checking whether the workflow requested model registration.",
                ),
            },
        )

        register_name = job.config.get("register_model_name")
        if register_name:
            best = _resolve_best(completed_experiments, job.problem_type)
            if best is not None:
                try:
                    from app.services.registry import register_experiment_as_model

                    with db.begin_nested():
                        model_version = register_experiment_as_model(
                            db,
                            experiment_id=best.id,
                            user_id=job.created_by,
                            model_name=str(register_name),
                            description=f"Auto-registered from training job {job.name}",
                            commit=False,
                        )
                    _log(
                        db,
                        job,
                        f"Auto-registered best run as {model_version.registered_model.name} v{model_version.version}.",
                    )
                except Exception as exc:
                    if _is_retryable(exc):
                        raise
                    logger.exception("Auto-registration failed", extra={"job_id": job.id})
                    _log(
                        db,
                        job,
                        f"Automatic model registration failed: {str(exc).splitlines()[0][:250]}",
                        level="warning",
                    )

        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.status_message = "Completed"
        job.completed_at = _now()
        if failures:
            job.error_message = (
                f"{len(failures)} algorithm run(s) failed: " + "; ".join(failures)
            )[:4000]
        _log(
            db,
            job,
            f"Job completed successfully with {successes}/{len(job.algorithms)} algorithm runs.",
        )
        db.add(job)
        _workflow_steps(
            db,
            job,
            {
                "register": (
                    "completed",
                    "Registration step finished; no request is also a valid outcome.",
                )
            },
        )
        _commit_terminal(db, job, lease)
    except LeaseLost:
        db.rollback()
        logger.warning("Training stopped after losing its lease", extra={"job_id": job_id})
        _reconcile_interrupted_job(job_id)
    except Exception as exc:
        logger.exception("Training runner crashed", extra={"job_id": job_id})
        db.rollback()
        if claimed:
            try:
                job = TrainingRepository(db).get_job_detail(job_id)
                if job is not None:
                    lease.guard(db)
                    if _is_retryable(exc):
                        _end_interrupted_attempt(
                            db,
                            job,
                            _now(),
                            "Temporary training dependency failure.",
                            allow_retry=True,
                        )
                        lease.commit(db)
                        if job.status != JobStatus.QUEUED:
                            TRAINING_JOBS.labels(status=job.status).inc()
                    else:
                        _mark_job_failed(
                            db, job, f"Training runner crashed: {str(exc).splitlines()[0][:300]}"
                        )
                        _commit_terminal(db, job, lease)
            except LeaseLost:
                db.rollback()
                _reconcile_interrupted_job(job_id)
            except Exception:
                logger.exception("Failed to mark crashed job as failed", extra={"job_id": job_id})
                db.rollback()
    finally:
        db.close()
        lease.close()
        if active:
            ACTIVE_TRAINING_JOBS.dec()
            logger.info("Training worker finished")
        request_id_ctx.reset(request_token)
        run_id_ctx.reset(run_token)


def _format_metrics(metrics: dict[str, Any]) -> str:
    parts = []
    for key in ("accuracy", "f1_weighted", "roc_auc", "rmse", "mae", "r2", "silhouette"):
        value = metrics.get(key)
        if isinstance(value, (int, float)) and math.isfinite(value):
            parts.append(f"{key}={value:.4f}")
    return ", ".join(parts)


def _is_retryable(exc: Exception) -> bool:
    # The dataset and algorithm adapters can wrap their original exception.
    return any(
        isinstance(error, (ConnectionError, TimeoutError, StorageConnectionError, ReadTimeoutError))
        or (isinstance(error, DBAPIError) and error.connection_invalidated)
        for error in (exc, exc.__cause__)
    )


def _deadline_passed(deadline: datetime | None, now: datetime) -> bool:
    if deadline is None:
        return False
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    return deadline <= now


def _end_interrupted_attempt(
    db: Session, job: TrainingJob, now: datetime, reason: str, *, allow_retry: bool
) -> None:
    policy = TrainingExecutionPolicy.model_validate(job.config.get("execution_policy", {}))
    budget = policy.max_attempts or get_settings().training_max_attempts
    retry = allow_retry and not job.cancel_requested and job.execution_attempt < budget
    for experiment in job.experiments:
        if experiment.status in {ExperimentStatus.RUNNING, ExperimentStatus.QUEUED}:
            experiment.status = (
                ExperimentStatus.CANCELLED if job.cancel_requested else ExperimentStatus.FAILED
            )
            experiment.error_message = reason
            experiment.completed_at = now

    job.execution_token = None
    job.lease_expires_at = None
    if retry:
        delay = min(300, policy.retry_backoff_seconds * 2 ** max(0, job.execution_attempt - 1))
        job.status = JobStatus.QUEUED
        job.status_message = "Queued for retry"
        job.progress = 0
        job.started_at = None
        job.execution_deadline_at = None
        job.cancel_deadline_at = None
        job.error_message = None
        db.add(TrainingDispatch(job_id=job.id, available_at=now + timedelta(seconds=delay)))
        _log(
            db,
            job,
            f"{reason} Attempt {job.execution_attempt + 1} eligible in {delay}s.",
            "warning",
        )
        return

    job.status = JobStatus.CANCELLED if job.cancel_requested else JobStatus.FAILED
    job.status_message = "Cancelled" if job.cancel_requested else "Failed"
    job.error_message = None if job.cancel_requested else reason
    job.completed_at = now
    job.progress = min(job.progress, 99)
    _log(db, job, reason, "warning")
    _finish_workflow(db, job)


def _reconcile_interrupted_job(job_id: str) -> None:
    try:
        recover_stale_jobs(job_id)
    except Exception:
        logger.exception("Could not reconcile interrupted training", extra={"job_id": job_id})


def recover_stale_jobs(job_id: str | None = None) -> int:
    settings = get_settings()
    now = _now()
    legacy_timeout = timedelta(minutes=settings.stale_job_after_minutes)
    if settings.job_execution_mode == "celery":
        from app.workers.celery_app import VISIBILITY_TIMEOUT_SECONDS

        legacy_timeout = max(legacy_timeout, timedelta(seconds=VISIBILITY_TIMEOUT_SECONDS))
    cutoff = now - legacy_timeout
    expired = or_(
        TrainingJob.lease_expires_at <= now,
        TrainingJob.execution_deadline_at <= now,
        TrainingJob.cancel_deadline_at <= now,
        and_(TrainingJob.execution_token.is_(None), TrainingJob.started_at < cutoff),
    )
    candidates = select(TrainingJob.id).where(TrainingJob.status == JobStatus.RUNNING, expired)
    if job_id is not None:
        candidates = candidates.where(TrainingJob.id == job_id)
    with SessionLocal() as db:
        job_ids = list(
            db.scalars(candidates.order_by(TrainingJob.lease_expires_at, TrainingJob.id).limit(100))
        )

    recovered = 0
    for candidate_id in job_ids:
        with SessionLocal.begin() as db:
            # Renewal and recovery serialize on the same row.
            matched = db.execute(
                update(TrainingJob)
                .where(
                    TrainingJob.id == candidate_id, TrainingJob.status == JobStatus.RUNNING, expired
                )
                .values(lease_expires_at=None)
            )
            if matched.rowcount != 1:
                continue
            job = db.get(TrainingJob, candidate_id)
            assert job is not None
            timed_out = _deadline_passed(job.execution_deadline_at, now)
            if job.cancel_requested:
                reason = "Training cancelled after the worker stopped or the cancellation deadline elapsed."
            elif timed_out:
                reason = "Training exceeded its execution deadline."
            else:
                reason = "Training worker lease expired."
            _end_interrupted_attempt(
                db, job, now, reason, allow_retry=job.execution_token is not None and not timed_out
            )
            status = job.status
            recovered += 1
        if status != JobStatus.QUEUED:
            TRAINING_JOBS.labels(status=status).inc()
    return recovered
