from __future__ import annotations

import contextlib
import json
import logging
import math
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import joblib
from sklearn.pipeline import Pipeline
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import TrainingError
from app.core.metrics import ACTIVE_TRAINING_JOBS, EXPERIMENTS, TRAINING_JOBS
from app.db.session import SessionLocal
from app.ml.algorithms import get_algorithm
from app.ml.evaluation import METRIC_DIRECTIONS, primary_metric
from app.ml.tracking import MLflowTracker, format_tracking_tags
from app.ml.training import TrainingConfig, train_algorithm
from app.ml.utils import float_or_none
from app.ml.validation import read_dataframe
from app.models.enums import ExperimentStatus, JobStatus
from app.models.training import Experiment, TrainingJob, TrainingJobLog
from app.repositories.training import TrainingRepository
from app.services.storage import get_storage, training_artifact_prefix

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
    job: TrainingJob, experiment: Experiment, pipeline: Pipeline, reference_profile: dict[str, Any]
) -> tuple[str, str]:
    storage = get_storage()
    prefix = training_artifact_prefix(job.id, experiment.id)
    with tempfile.TemporaryDirectory() as temp_directory:
        directory = Path(temp_directory)
        model_path = directory / "model.joblib"
        reference_path = directory / "reference_profile.json"
        joblib.dump(pipeline, model_path)
        reference_path.write_text(json.dumps(reference_profile, indent=2), encoding="utf-8")
        try:
            reloaded = joblib.load(model_path)
            if not hasattr(reloaded, "predict"):
                raise TrainingError("Serialized model could not be validated.")
        except Exception as exc:
            raise TrainingError(f"Model artifact validation failed: {exc}") from exc
        storage.put_file(f"{prefix}/model.joblib", model_path)
        storage.put_file(f"{prefix}/reference_profile.json", reference_path)
        return f"{prefix}/model.joblib", f"{prefix}/reference_profile.json"


def _mark_job_failed(db: Session, job: TrainingJob, message: str) -> None:
    job.status = JobStatus.FAILED
    job.error_message = message[:4000]
    job.completed_at = _now()
    job.status_message = "Failed"
    _log(db, job, message, level="error")
    db.add(job)
    TRAINING_JOBS.labels(status="failed").inc()
    db.commit()


def _workflow_steps(db: Session, job: TrainingJob, updates: dict[str, tuple[str, str]]) -> None:
    workflow_id = (job.config or {}).get("workflow_run_id")
    if not workflow_id:
        return
    from app.models.modelops import WorkflowRun

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
    db.commit()


def execute_training_job(job_id: str) -> None:
    db = SessionLocal()
    job: TrainingJob | None = None
    try:
        repository = TrainingRepository(db)
        claimed = repository.claim_job(job_id, _now())
        db.commit()
        if not claimed:
            db.rollback()
            return
        job = repository.get_job_detail(job_id)
        if job is None:
            db.rollback()
            return
        ACTIVE_TRAINING_JOBS.inc()
        _log(db, job, "Worker claimed the job; loading dataset.", level="info")
        _progress(db, job, 3, "Loading dataset")
        db.commit()

        dataset_version = job.dataset_version
        storage = get_storage()
        with storage.open_path(dataset_version.storage_key) as dataset_path:
            df = read_dataframe(dataset_path, dataset_version.original_filename)
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
        db.commit()

        training_config = TrainingConfig(
            problem_type=job.problem_type,
            target_column=job.target_column,
            feature_columns=job.feature_columns,
            test_size=float(job.config.get("test_size", 0.2)),
            random_seed=int(job.config.get("random_seed", 42)),
            cv_folds=int(job.config.get("cv_folds", 0)),
            sensitive_columns=list(job.config.get("sensitive_columns", [])),
        )
        experiments: list[Experiment] = []
        for selection in job.algorithms:
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
        db.flush()
        db.commit()

        project_slug = job.project.slug if job.project else "project"
        tracker = MLflowTracker()
        total = len(experiments)
        successes = 0
        failures: list[str] = []

        for index, experiment in enumerate(experiments):
            db.refresh(job)
            if job.cancel_requested:
                break
            selection = job.algorithms[index]
            spec = get_algorithm(selection["algorithm"], job.problem_type)
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
            db.commit()

            try:
                result = train_algorithm(
                    df,
                    spec,
                    selection.get("hyperparameters", {}),
                    training_config,
                )
                artifact_key, reference_key = _persist_artifacts(
                    job, experiment, result.pipeline, result.reference_profile
                )
                for warning in result.warnings:
                    _record_tracking_failure(db, job, warning)

                run_id = None
                tracking_warning = None
                with tempfile.TemporaryDirectory() as temp_directory:
                    directory = Path(temp_directory)
                    model_path = directory / "model.joblib"
                    reference_path = directory / "reference_profile.json"
                    joblib.dump(result.pipeline, model_path)
                    reference_path.write_text(
                        json.dumps(result.reference_profile, indent=2), encoding="utf-8"
                    )
                    run_id, tracking_warning = tracker.log_run(
                        experiment_name=f"atlas-{project_slug}",
                        run_name=experiment.name,
                        params=experiment.params,
                        metrics=result.metrics,
                        tags=format_tracking_tags(
                            job.id, job.project_id, job.dataset_version_id, job.problem_type
                        ),
                        artifact_paths=[model_path, reference_path],
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
                EXPERIMENTS.labels(status="completed", algorithm=spec.id).inc()
                _log(
                    db,
                    job,
                    f"{spec.label} completed in {result.duration_seconds:.1f}s. "
                    f"{_format_metrics(result.metrics)}",
                )
            except TrainingError as exc:
                message = str(exc)
                experiment.status = ExperimentStatus.FAILED
                experiment.error_message = message[:4000]
                experiment.completed_at = _now()
                failures.append(f"{spec.label}: {message}")
                EXPERIMENTS.labels(status="failed", algorithm=spec.id).inc()
                _log(db, job, f"{spec.label} failed: {message}", level="error")
            except Exception as exc:  # unexpected algorithm error
                message = str(exc).splitlines()[0][:300] or exc.__class__.__name__
                experiment.status = ExperimentStatus.FAILED
                experiment.error_message = f"Unexpected training error: {message}"
                experiment.completed_at = _now()
                failures.append(f"{spec.label}: {message}")
                EXPERIMENTS.labels(status="failed", algorithm=spec.id).inc()
                logger.exception("Unexpected training failure", extra={"job_id": job.id})
                _log(db, job, f"{spec.label} failed unexpectedly: {message}", level="error")
            db.add(experiment)
            _progress(
                db,
                job,
                10 + int(((index + 1) / max(total, 1)) * 85),
                f"Completed {index + 1}/{total} algorithm run(s)",
            )
            db.commit()

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
            TRAINING_JOBS.labels(status="cancelled").inc()
            db.add(job)
            db.commit()
            return

        completed_experiments = [
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

                    version = register_experiment_as_model(
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
                        f"Auto-registered best run as {version.registered_model.name} v{version.version}.",
                    )
                except Exception as exc:
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
            f"Job completed successfully with {successes}/{total} algorithm runs.",
        )
        TRAINING_JOBS.labels(status="completed").inc()
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
        db.commit()
    except Exception as exc:
        logger.exception("Training runner crashed", extra={"job_id": job_id})
        db.rollback()
        try:
            if job is None:
                job = TrainingRepository(db).get_job_detail(job_id)
            if job is not None and job.status not in {
                JobStatus.COMPLETED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            }:
                _mark_job_failed(
                    db,
                    job,
                    f"Training runner crashed: {str(exc).splitlines()[0][:300]}",
                )
        except Exception:
            logger.exception("Failed to mark crashed job as failed", extra={"job_id": job_id})
    finally:
        if job is not None and (job.config or {}).get("workflow_run_id"):
            try:
                from app.models.modelops import WorkflowRun

                workflow_run = db.get(WorkflowRun, job.config["workflow_run_id"])
                if workflow_run is not None:
                    workflow_run.status = str(job.status)
                    workflow_run.error_message = job.error_message
                    workflow_run.completed_at = job.completed_at or _now()
                    step_states = list(workflow_run.step_states or [])
                    terminal = str(job.status)
                    for step in step_states:
                        if step.get("status") in {"queued", "running"}:
                            step["status"] = (
                                "completed" if terminal == JobStatus.COMPLETED else terminal
                            )
                    workflow_run.step_states = step_states
                    db.add(workflow_run)
                    db.commit()
            except Exception:
                logger.exception("Could not finalize workflow run", extra={"job_id": job_id})
                db.rollback()
        with contextlib.suppress(Exception):
            ACTIVE_TRAINING_JOBS.dec()
        db.close()


def _format_metrics(metrics: dict[str, Any]) -> str:
    parts = []
    for key in ("accuracy", "f1_weighted", "roc_auc", "rmse", "mae", "r2", "silhouette"):
        value = metrics.get(key)
        if isinstance(value, (int, float)) and math.isfinite(value):
            parts.append(f"{key}={value:.4f}")
    return ", ".join(parts)


def recover_stale_jobs(settings_override: Any | None = None) -> int:
    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.stale_job_after_minutes)
    db = SessionLocal()
    try:
        stale = (
            db.query(TrainingJob)
            .filter(TrainingJob.status == JobStatus.RUNNING, TrainingJob.started_at < cutoff)
            .all()
        )
        for job in stale:
            job.status = JobStatus.FAILED
            job.error_message = (
                "Job was marked as failed by startup recovery after exceeding the stale threshold."
            )
            job.completed_at = _now()
            job.progress = min(job.progress, 99)
            job.status_message = "Failed (stale)"
            db.add(TrainingJobLog(job_id=job.id, level="error", message=job.error_message))
            for experiment in job.experiments:
                if experiment.status in {ExperimentStatus.RUNNING, ExperimentStatus.QUEUED}:
                    experiment.status = ExperimentStatus.FAILED
                    experiment.error_message = "Recovered as failed after worker loss."
                    experiment.completed_at = _now()
                    db.add(experiment)
            db.add(job)
        db.commit()
        return len(stale)
    finally:
        db.close()
