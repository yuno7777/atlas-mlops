from __future__ import annotations

import logging
import math
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.metrics import DRIFT_DETECTIONS
from app.db.session import SessionLocal
from app.ml.algorithms import get_algorithm, validate_hyperparameters
from app.ml.drift import analyze_drift
from app.ml.evaluation import metric_directions, primary_metric
from app.ml.utils import float_or_none
from app.models.dataset import DatasetVersion
from app.models.deployment import Deployment
from app.models.enums import ExperimentStatus, JobStatus
from app.models.monitoring import MonitoringResult
from app.models.training import Experiment, TrainingJob
from app.models.user import Project, User
from app.repositories.deployments import DeploymentRepository
from app.repositories.monitoring import MonitoringRepository
from app.repositories.training import ExperimentRepository, TrainingRepository
from app.schemas.experiment import ExperimentSummary
from app.schemas.monitoring import (
    IncumbentInfo,
    MonitoringResultOut,
    RetrainComparisonResponse,
    RetrainRequest,
    TimeseriesPoint,
    TimeseriesResponse,
)
from app.schemas.training import (
    AlgorithmSelection,
    TrainingJobCreateRequest,
    TrainingJobDetail,
)
from app.services.access import require_project
from app.services.audit import record_audit
from app.services.training import create_training_job, experiment_summary

logger = logging.getLogger(__name__)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _result_out(result: MonitoringResult) -> MonitoringResultOut:
    return MonitoringResultOut(
        id=result.id,
        deployment_id=result.deployment_id,
        model_version_id=result.model_version_id,
        status=result.status,
        sample_count=result.sample_count,
        labeled_count=result.labeled_count,
        data_drift_detected=result.data_drift_detected,
        prediction_drift_detected=result.prediction_drift_detected,
        concept_drift_detected=result.concept_drift_detected,
        drift_share=result.drift_share,
        psi_max=result.psi_max,
        ks_min_pvalue=result.ks_min_pvalue,
        details=result.details,
        created_at=result.created_at,
    )


def _monitoring_samples(
    db: Session, deployment: Deployment, since: datetime
) -> list[dict[str, Any]]:
    logs = DeploymentRepository(db).predictions_since(deployment.id, since, variant="champion")
    samples = []
    for log in logs:
        prediction = log.prediction
        if isinstance(prediction, dict):
            prediction = prediction.get("prediction")
        samples.append(
            {
                "features": log.features,
                "prediction": prediction,
                "status": log.status,
                "actual": log.actual,
                "created_at": _utc(log.created_at),
            }
        )
    return samples


def analyze_deployment(db: Session, deployment: Deployment) -> MonitoringResult:
    repository = MonitoringRepository(db)
    previous = repository.latest(deployment.id)
    config = deployment.config or {}
    window_hours = int(config.get("window_hours", 24))
    since = datetime.now(UTC) - timedelta(hours=window_hours)
    samples = _monitoring_samples(db, deployment, since)
    version = deployment.model_version
    reference_profile = version.reference_profile or {}
    experiment = version.experiment
    problem_type = str(
        reference_profile.get("problem_type")
        or (experiment.problem_type if experiment else "classification")
    )
    outcome = analyze_drift(reference_profile, samples, problem_type, config, window_hours)
    result = MonitoringResult(
        deployment_id=deployment.id,
        model_version_id=deployment.model_version_id,
        status=outcome["status"],
        sample_count=int(outcome["sample_count"]),
        labeled_count=int(outcome["labeled_count"]),
        data_drift_detected=bool(outcome["data_drift_detected"]),
        prediction_drift_detected=bool(outcome["prediction_drift_detected"]),
        concept_drift_detected=bool(outcome["concept_drift_detected"]),
        drift_share=float(outcome["drift_share"]),
        psi_max=float(outcome["psi_max"]),
        ks_min_pvalue=outcome["ks_min_pvalue"],
        details=outcome["details"],
    )
    db.add(result)
    db.flush()
    DRIFT_DETECTIONS.labels(deployment_id=deployment.id, status=result.status).inc()
    if result.status in {"warning", "critical"} and (
        previous is None or previous.status != result.status
    ):
        from app.models.deployment import DeploymentEvent

        db.add(
            DeploymentEvent(
                deployment_id=deployment.id,
                level="warning" if result.status == "warning" else "error",
                message=(
                    f"Monitoring status is {result.status}: "
                    f"drift share {result.drift_share:.0%}, max PSI {result.psi_max:.2f}."
                ),
                details={
                    "monitoring_result_id": result.id,
                    "drifted_features": outcome["details"].get("drifted_features", []),
                },
            )
        )
        from app.services.alerts import dispatch_monitoring_alerts

        dispatch_monitoring_alerts(db, deployment, result)
    return result


def run_monitoring(
    db: Session, user: User, deployment_id: str, ip_address: str | None = None
) -> MonitoringResultOut:
    repository = DeploymentRepository(db)
    deployment = repository.get(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    project, _role = require_project(db, user, deployment.project_id, write=True)
    result = analyze_deployment(db, deployment)
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="monitoring.run",
        resource_type="deployment",
        resource_id=deployment.id,
        details={"monitoring_result_id": result.id, "status": result.status},
        ip_address=ip_address,
    )
    db.commit()
    from app.services.rollouts import advance_active_rollouts

    advance_active_rollouts(db)
    _maybe_auto_retrain(db, deployment, result)
    return _result_out(result)


def latest_monitoring(db: Session, user: User, deployment_id: str) -> MonitoringResultOut:
    deployment = DeploymentRepository(db).get(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    require_project(db, user, deployment.project_id)
    result = MonitoringRepository(db).latest(deployment_id)
    if result is None:
        raise NotFoundError("No monitoring results are available for this deployment.")
    return _result_out(result)


def list_monitoring(
    db: Session,
    user: User,
    deployment_id: str,
    *,
    page: int,
    page_size: int,
) -> tuple[list[MonitoringResultOut], int]:
    deployment = DeploymentRepository(db).get(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    require_project(db, user, deployment.project_id)
    results, total = MonitoringRepository(db).list(deployment_id, (page - 1) * page_size, page_size)
    return [_result_out(result) for result in results], total


def monitoring_timeseries(
    db: Session, user: User, deployment_id: str, hours: int
) -> TimeseriesResponse:
    deployment = DeploymentRepository(db).get(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    require_project(db, user, deployment.project_id)
    now = datetime.now(UTC)
    end_bucket = now.replace(minute=0, second=0, microsecond=0)
    start_bucket = end_bucket - timedelta(hours=max(0, hours - 1))
    logs = DeploymentRepository(db).predictions_since(deployment.id, start_bucket)
    buckets: dict[datetime, list] = {
        start_bucket + timedelta(hours=offset): [] for offset in range(hours)
    }
    for log in logs:
        created = _utc(log.created_at)
        if created is None:
            continue
        bucket = created.replace(minute=0, second=0, microsecond=0)
        if bucket in buckets:
            buckets[bucket].append(log)
    points: list[TimeseriesPoint] = []
    for bucket in sorted(buckets):
        entries = buckets[bucket]
        latencies = sorted(float(entry.latency_ms or 0.0) for entry in entries)
        average = sum(latencies) / len(latencies) if latencies else 0.0
        if latencies:
            rank = max(1, math.ceil(0.95 * len(latencies)))
            p95 = latencies[min(len(latencies) - 1, rank - 1)]
        else:
            p95 = 0.0
        points.append(
            TimeseriesPoint(
                bucket=bucket,
                predictions=len(entries),
                failures=sum(1 for entry in entries if entry.status == "failed"),
                avg_latency_ms=round(average, 3),
                p95_latency_ms=round(p95, 3),
            )
        )
    return TimeseriesResponse(deployment_id=deployment.id, hours=hours, points=points)


def _hyperparameters_for(version) -> dict[str, Any]:
    spec = get_algorithm(version.algorithm, version.experiment.problem_type)
    allowed = {hyperparameter.name for hyperparameter in spec.hyperparameters}
    provided = {key: value for key, value in (version.params or {}).items() if key in allowed}
    return validate_hyperparameters(spec, provided)


def _active_retrain_job(db: Session, deployment_id: str) -> TrainingJob | None:
    return db.execute(
        select(TrainingJob)
        .where(
            TrainingJob.retrain_source_deployment_id == deployment_id,
            TrainingJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
        .order_by(TrainingJob.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _build_retrain_payload(
    deployment: Deployment,
    dataset_version_id: str | None,
    name: str | None,
) -> TrainingJobCreateRequest:
    version = deployment.model_version
    experiment = version.experiment
    if experiment is None:
        raise ConflictError("The deployed model version has no training experiment.")
    job = experiment.job
    params = version.params or {}
    test_size = float(params.get("test_size", 0.2))
    random_seed = int(params.get("random_seed", 42))
    cv_folds = int(params.get("cv_folds", 0))
    return TrainingJobCreateRequest(
        project_id=deployment.project_id,
        dataset_version_id=dataset_version_id or experiment.dataset_version_id,
        name=name or f"Retrain · {deployment.name} · {datetime.now(UTC).strftime('%b %d, %H:%M')}",
        problem_type=experiment.problem_type,
        target_column=job.target_column if job else None,
        feature_columns=job.feature_columns if job else None,
        algorithms=[
            AlgorithmSelection(
                algorithm=version.algorithm,
                hyperparameters=_hyperparameters_for(version),
            )
        ],
        test_size=min(0.4, max(0.1, test_size)),
        random_seed=max(0, random_seed),
        cv_folds=min(10, max(0, cv_folds)),
        register_model_name=None,
    )


def _create_retrain_job(
    db: Session,
    deployment: Deployment,
    *,
    user: User,
    dataset_version_id: str | None,
    name: str | None,
    ip_address: str | None = None,
) -> TrainingJobDetail:
    payload = _build_retrain_payload(deployment, dataset_version_id, name)
    dataset_version = db.get(DatasetVersion, payload.dataset_version_id)
    if dataset_version is None or dataset_version.dataset.project_id != deployment.project_id:
        raise NotFoundError("Dataset version not found.")
    detail = create_training_job(
        db,
        user,
        payload,
        ip_address,
        retrain_source_deployment_id=deployment.id,
    )
    deployment.last_retrain_at = datetime.now(UTC)
    db.add(deployment)
    db.commit()
    return detail


def retrain_deployment(
    db: Session,
    user: User,
    deployment_id: str,
    payload: RetrainRequest,
    ip_address: str | None = None,
) -> TrainingJobDetail:
    deployment = DeploymentRepository(db).get(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    project, _role = require_project(db, user, deployment.project_id, write=True)
    detail = _create_retrain_job(
        db,
        deployment,
        user=user,
        dataset_version_id=payload.dataset_version_id,
        name=payload.name,
        ip_address=ip_address,
    )
    from app.models.deployment import DeploymentEvent

    db.add(
        DeploymentEvent(
            deployment_id=deployment.id,
            level="info",
            message=f"Manual retraining job queued ({detail.name}).",
            details={"training_job_id": detail.id},
        )
    )
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="deployment.retrain_requested",
        resource_type="deployment",
        resource_id=deployment.id,
        details={"training_job_id": detail.id},
        ip_address=ip_address,
    )
    db.commit()
    return detail


def _maybe_auto_retrain(
    db: Session, deployment: Deployment, result: MonitoringResult
) -> TrainingJob | None:
    config = deployment.config or {}
    drift_detected = (
        result.data_drift_detected
        or result.prediction_drift_detected
        or result.concept_drift_detected
    )
    if not config.get("auto_retrain_on_drift", False) or not drift_detected:
        return None
    cooldown_hours = int(config.get("auto_retrain_cooldown_hours", 12))
    last_retrain = _utc(deployment.last_retrain_at)
    if last_retrain is not None and datetime.now(UTC) - last_retrain < timedelta(
        hours=cooldown_hours
    ):
        return None
    if _active_retrain_job(db, deployment.id) is not None:
        return None
    user = db.get(User, deployment.created_by)
    if user is None:
        return None
    project = db.get(Project, deployment.project_id)
    from app.models.deployment import DeploymentEvent

    try:
        detail = _create_retrain_job(
            db,
            deployment,
            user=user,
            dataset_version_id=None,
            name=f"Drift retrain · {deployment.name} · {datetime.now(UTC).strftime('%b %d, %H:%M')}",
        )
        db.refresh(deployment)
        db.add(
            DeploymentEvent(
                deployment_id=deployment.id,
                level="warning",
                message="Drift detected; automatic retraining job queued. Promotion remains manual.",
                details={
                    "training_job_id": detail.id,
                    "monitoring_result_id": result.id,
                    "status": result.status,
                },
            )
        )
        if project is not None:
            record_audit(
                db,
                workspace_id=project.workspace_id,
                project_id=project.id,
                user_id=None,
                action="deployment.auto_retrain_requested",
                resource_type="deployment",
                resource_id=deployment.id,
                details={
                    "training_job_id": detail.id,
                    "monitoring_result_id": result.id,
                    "drift_share": result.drift_share,
                },
            )
        db.commit()
        return TrainingRepository(db).get_job(detail.id)
    except Exception as exc:
        logger.exception("Automatic retraining failed", extra={"deployment_id": deployment.id})
        db.rollback()
        try:
            db.add(
                DeploymentEvent(
                    deployment_id=deployment.id,
                    level="error",
                    message=f"Automatic retraining could not be started: {str(exc).splitlines()[0][:250]}",
                    details={"monitoring_result_id": result.id},
                )
            )
            db.commit()
        except Exception:
            db.rollback()
        return None


def scan_active_deployments() -> int:
    settings = get_settings()
    db = SessionLocal()
    analyzed = 0
    try:
        deployments = DeploymentRepository(db).list_all_active()
        for deployment in deployments:
            try:
                repository = MonitoringRepository(db)
                latest = repository.latest(deployment.id)
                latest_at = _utc(latest.created_at) if latest else None
                if latest_at is not None and datetime.now(UTC) - latest_at < timedelta(
                    seconds=max(60, int(settings.monitoring_interval_seconds * 0.5))
                ):
                    continue
                result = analyze_deployment(db, deployment)
                db.commit()
                _maybe_auto_retrain(db, deployment, result)
                analyzed += 1
            except Exception:
                logger.exception(
                    "Scheduled monitoring failed", extra={"deployment_id": deployment.id}
                )
                db.rollback()
        try:
            from app.services.rollouts import advance_active_rollouts

            advance_active_rollouts(db)
        except Exception:
            logger.exception("Progressive rollout evaluation failed")
            db.rollback()
        try:
            from app.services.workflows import process_due_pipeline_runs

            process_due_pipeline_runs()
        except Exception:
            logger.exception("Scheduled workflow processing failed")
        return analyzed
    finally:
        db.close()


def retrain_comparison(db: Session, user: User, deployment_id: str) -> RetrainComparisonResponse:
    deployment = DeploymentRepository(db).get(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    require_project(db, user, deployment.project_id)
    version = deployment.model_version
    experiment = version.experiment
    if experiment is None:
        raise ConflictError("The deployed model version has no training experiment.")
    problem_type = experiment.problem_type
    incumbent_metrics = version.metrics or {}
    jobs = list(
        db.execute(
            select(TrainingJob)
            .where(TrainingJob.retrain_source_deployment_id == deployment.id)
            .order_by(TrainingJob.created_at.desc())
            .limit(10)
        )
        .scalars()
        .all()
    )
    latest_job = jobs[0] if jobs else None
    candidate_experiments: list[Experiment] = []
    if latest_job is not None:
        candidate_experiments = list(
            db.execute(
                select(Experiment)
                .options(joinedload(Experiment.dataset_version).joinedload(DatasetVersion.dataset))
                .where(
                    Experiment.training_job_id == latest_job.id,
                    Experiment.status == ExperimentStatus.COMPLETED,
                )
                .order_by(Experiment.created_at.asc())
            )
            .scalars()
            .unique()
            .all()
        )
    registrations = ExperimentRepository(db).registrations_for(
        [candidate.id for candidate in candidate_experiments]
    )
    candidates: list[ExperimentSummary] = [
        experiment_summary(candidate, registration=registrations.get(candidate.id))
        for candidate in candidate_experiments
    ]
    directions = metric_directions(problem_type)
    metric_keys = [
        key
        for key in directions
        if _has_numeric(incumbent_metrics.get(key))
        or any(_has_numeric(candidate.metrics.get(key)) for candidate in candidates)
    ]
    deltas: dict[str, dict[str, float]] = {}
    for candidate in candidates:
        candidate_deltas: dict[str, float] = {}
        for metric in metric_keys:
            incumbent_value = float_or_none(incumbent_metrics.get(metric))
            candidate_value = float_or_none(candidate.metrics.get(metric))
            if incumbent_value is None or candidate_value is None:
                continue
            candidate_deltas[metric] = candidate_value - incumbent_value
        deltas[candidate.id] = candidate_deltas
    primary = primary_metric(problem_type)
    direction = directions.get(primary, "max")
    scored = [
        (candidate, float_or_none(candidate.metrics.get(primary))) for candidate in candidates
    ]
    scored = [(candidate, value) for candidate, value in scored if value is not None]
    recommended_id: str | None = None
    reason = "No completed retraining experiments are available to compare."
    if scored:
        best_candidate, best_value = (
            max(scored, key=lambda item: item[1])
            if direction == "max"
            else min(scored, key=lambda item: item[1])
        )
        incumbent_value = float_or_none(incumbent_metrics.get(primary))
        if incumbent_value is None:
            recommended_id = best_candidate.id
            reason = (
                f"{best_candidate.algorithm_label} is the strongest candidate with "
                f"{primary}={best_value:.4f}; the incumbent has no baseline value."
            )
        elif (direction == "max" and best_value > incumbent_value) or (
            direction == "min" and best_value < incumbent_value
        ):
            recommended_id = best_candidate.id
            delta = best_value - incumbent_value
            reason = (
                f"{best_candidate.algorithm_label} improves {primary} by {abs(delta):.4f} "
                f"versus the deployed version. Promotion remains explicit."
            )
        else:
            reason = (
                f"No retraining candidate surpasses the deployed {primary} of "
                f"{incumbent_value:.4f}. Keep the incumbent."
            )
    return RetrainComparisonResponse(
        deployment_id=deployment.id,
        incumbent=IncumbentInfo(
            model_version_id=version.id,
            version=version.version,
            algorithm=version.algorithm,
            metrics=incumbent_metrics,
        ),
        candidates=candidates,
        metric_keys=metric_keys,
        directions={key: directions[key] for key in metric_keys},
        deltas=deltas,
        recommended_experiment_id=recommended_id,
        recommendation_reason=reason,
        latest_job_id=latest_job.id if latest_job else None,
        latest_job_status=latest_job.status if latest_job else None,
    )


def _has_numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
