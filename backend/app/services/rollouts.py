from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.deployment import Deployment, DeploymentEvent, DeploymentRevision, PredictionLog
from app.models.enums import ModelStage
from app.models.modelops import DeploymentRollout
from app.models.registry import ModelVersion
from app.models.user import Project, User
from app.schemas.modelops import ReleaseGates, RolloutResponse, RolloutStartRequest
from app.services.access import require_project
from app.services.audit import record_audit


def _out(rollout: DeploymentRollout) -> RolloutResponse:
    traffic_steps = list(rollout.traffic_steps or [])
    step = min(max(rollout.current_step, 0), max(len(traffic_steps) - 1, 0))
    return RolloutResponse(
        id=rollout.id,
        deployment_id=rollout.deployment_id,
        candidate_version_id=rollout.candidate_version_id,
        status=rollout.status,
        traffic_steps=traffic_steps,
        current_step=rollout.current_step,
        current_traffic_percent=traffic_steps[step] if traffic_steps else 0,
        gates=rollout.gates,
        last_evaluation=rollout.last_evaluation,
        started_at=rollout.started_at,
        step_started_at=rollout.step_started_at,
        last_evaluated_at=rollout.last_evaluated_at,
        completed_at=rollout.completed_at,
        created_at=rollout.created_at,
    )


def get_rollout(db: Session, user: User, deployment_id: str) -> RolloutResponse | None:
    deployment = db.get(Deployment, deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    require_project(db, user, deployment.project_id)
    rollout = db.execute(
        select(DeploymentRollout)
        .where(DeploymentRollout.deployment_id == deployment_id)
        .order_by(DeploymentRollout.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return _out(rollout) if rollout else None


def start_rollout(
    db: Session,
    user: User,
    deployment_id: str,
    payload: RolloutStartRequest,
    ip_address: str | None = None,
) -> RolloutResponse:
    deployment = db.get(Deployment, deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    project, _ = require_project(db, user, deployment.project_id, write=True)
    if deployment.status != "active":
        raise ConflictError("Start the deployment before beginning a rollout.")
    active = db.execute(
        select(DeploymentRollout.id).where(
            DeploymentRollout.deployment_id == deployment.id,
            DeploymentRollout.status == "running",
        )
    ).scalar_one_or_none()
    if active:
        raise ConflictError("A progressive rollout is already running for this deployment.")
    candidate_id = payload.model_version_id or deployment.challenger_model_version_id
    if not candidate_id:
        raise ValidationError("Select a challenger model version to roll out.")
    candidate = db.get(ModelVersion, candidate_id)
    if candidate is None or candidate.registered_model.project_id != project.id:
        raise NotFoundError("Candidate model version not found.")
    if candidate.registered_model_id != deployment.registered_model_id:
        raise ConflictError("The rollout candidate must belong to the deployed registered model.")
    if candidate.id == deployment.model_version_id or candidate.stage == ModelStage.ARCHIVED:
        raise ConflictError(
            "The rollout candidate must be a non-archived version other than the champion."
        )
    deployment.challenger_model_version_id = candidate.id
    deployment.challenger_traffic_percent = payload.traffic_steps[0]
    now = datetime.now(UTC)
    rollout = DeploymentRollout(
        deployment_id=deployment.id,
        candidate_version_id=candidate.id,
        status="running",
        traffic_steps=payload.traffic_steps,
        current_step=0,
        gates=payload.gates.model_dump(),
        last_evaluation={"decision": "collecting", "reason": "Waiting for minimum traffic sample."},
        started_at=now,
        step_started_at=now,
        created_by=user.id,
    )
    db.add(rollout)
    db.flush()
    db.add(
        DeploymentEvent(
            deployment_id=deployment.id,
            level="info",
            message=f"Progressive rollout started at {payload.traffic_steps[0]}% challenger traffic.",
            details={
                "rollout_id": rollout.id,
                "candidate_version_id": candidate.id,
                "traffic_steps": payload.traffic_steps,
                "gates": payload.gates.model_dump(),
            },
        )
    )
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="deployment.rollout_started",
        resource_type="deployment",
        resource_id=deployment.id,
        details={
            "rollout_id": rollout.id,
            "candidate_version_id": candidate.id,
            "traffic_steps": payload.traffic_steps,
        },
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(rollout)
    return _out(rollout)


def cancel_rollout(
    db: Session, user: User, deployment_id: str, ip_address: str | None = None
) -> RolloutResponse:
    deployment = db.get(Deployment, deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    project, _ = require_project(db, user, deployment.project_id, write=True)
    rollout = db.execute(
        select(DeploymentRollout)
        .where(
            DeploymentRollout.deployment_id == deployment_id, DeploymentRollout.status == "running"
        )
        .order_by(DeploymentRollout.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if rollout is None:
        raise ConflictError("There is no active rollout to cancel.")
    deployment.challenger_traffic_percent = 0
    rollout.status = "cancelled"
    rollout.completed_at = datetime.now(UTC)
    rollout.last_evaluation = {"decision": "cancelled", "reason": "Cancelled by a project user."}
    db.add(
        DeploymentEvent(
            deployment_id=deployment.id,
            level="warning",
            message="Progressive rollout cancelled; traffic returned to the champion.",
            details={"rollout_id": rollout.id},
        )
    )
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="deployment.rollout_cancelled",
        resource_type="deployment",
        resource_id=deployment.id,
        details={"rollout_id": rollout.id},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(rollout)
    return _out(rollout)


def _value(prediction: Any) -> Any:
    if isinstance(prediction, dict):
        return prediction.get("prediction")
    return prediction


def _normalized(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("prediction")
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip().lower()


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _quality(logs: list[PredictionLog], problem_type: str) -> tuple[float | None, int]:
    labeled = [log for log in logs if log.status == "success" and log.actual is not None]
    if not labeled:
        return None, 0
    if problem_type == "classification":
        correct = sum(
            _normalized(_value(log.prediction)) == _normalized(log.actual) for log in labeled
        )
        return correct / len(labeled), len(labeled)
    errors: list[float] = []
    for log in labeled:
        try:
            errors.append(abs(float(_value(log.prediction)) - float(log.actual)))
        except (TypeError, ValueError):
            continue
    return (sum(errors) / len(errors), len(errors)) if errors else (None, 0)


def _evaluate(db: Session, rollout: DeploymentRollout, deployment: Deployment) -> dict[str, Any]:
    rows = list(
        db.execute(
            select(PredictionLog).where(
                PredictionLog.deployment_id == deployment.id,
                PredictionLog.created_at >= rollout.started_at,
                PredictionLog.model_version_id.in_(
                    [deployment.model_version_id, rollout.candidate_version_id]
                ),
            )
        ).scalars()
    )
    challenger = [row for row in rows if row.model_version_id == rollout.candidate_version_id]
    champion = [row for row in rows if row.model_version_id == deployment.model_version_id]
    step_started_at = _utc(rollout.step_started_at)
    stage_challenger = [row for row in challenger if _utc(row.created_at) >= step_started_at]
    candidate_samples = len(stage_challenger)
    candidate_failures = sum(row.status != "success" for row in stage_challenger)
    error_rate = candidate_failures / candidate_samples if candidate_samples else 0.0
    latencies = sorted(row.latency_ms for row in stage_challenger if row.status == "success")
    p95 = (
        latencies[min(math.ceil(0.95 * len(latencies)) - 1, len(latencies) - 1)]
        if latencies
        else None
    )
    problem_type = deployment.model_version.experiment.problem_type
    challenger_quality, challenger_labeled = _quality(challenger, problem_type)
    champion_quality, champion_labeled = _quality(champion, problem_type)
    gates = ReleaseGates.model_validate(rollout.gates)
    quality_regression: float | None = None
    if challenger_quality is not None and champion_quality is not None:
        if problem_type == "classification":
            quality_regression = champion_quality - challenger_quality
        else:
            quality_regression = (challenger_quality - champion_quality) / max(
                abs(champion_quality), 1e-9
            )
    report: dict[str, Any] = {
        "decision": "awaiting_samples",
        "candidate_samples": candidate_samples,
        "candidate_failures": candidate_failures,
        "candidate_error_rate": round(error_rate, 6),
        "candidate_p95_latency_ms": round(p95, 3) if p95 is not None else None,
        "challenger_labeled_samples": challenger_labeled,
        "champion_labeled_samples": champion_labeled,
        "challenger_quality": challenger_quality,
        "champion_quality": champion_quality,
        "quality_regression": quality_regression,
        "checked_at": datetime.now(UTC).isoformat(),
    }
    if candidate_samples < gates.min_samples:
        report["reason"] = (
            f"Need {gates.min_samples - candidate_samples} more challenger request(s)."
        )
        return report
    if error_rate > gates.max_error_rate:
        report.update(decision="rollback", reason="Candidate error rate exceeded the release gate.")
        return report
    if p95 is not None and p95 > gates.max_p95_latency_ms:
        report.update(
            decision="rollback", reason="Candidate p95 latency exceeded the release gate."
        )
        return report
    if gates.min_labeled_samples and (
        challenger_labeled < gates.min_labeled_samples
        or champion_labeled < gates.min_labeled_samples
    ):
        report.update(
            decision="awaiting_feedback",
            reason=f"Need {gates.min_labeled_samples} labeled requests for both variants before evaluating quality.",
        )
        return report
    if quality_regression is not None and quality_regression > gates.max_metric_regression:
        report.update(
            decision="rollback", reason="Candidate quality regressed beyond the release gate."
        )
        return report
    if quality_regression is None and gates.min_labeled_samples == 0:
        report["quality_gate"] = "skipped_by_configuration"
    else:
        report["quality_gate"] = "passed"
    report.update(decision="advance", reason="All configured release gates passed.")
    return report


def _finish_promotion(db: Session, rollout: DeploymentRollout, deployment: Deployment) -> None:
    now = datetime.now(UTC)
    version = db.get(ModelVersion, rollout.candidate_version_id)
    db.execute(
        update(DeploymentRevision)
        .where(
            DeploymentRevision.deployment_id == deployment.id,
            DeploymentRevision.deactivated_at.is_(None),
        )
        .values(deactivated_at=now)
    )
    deployment.model_version_id = version.id
    deployment.registered_model_id = version.registered_model_id
    deployment.challenger_model_version_id = None
    deployment.challenger_traffic_percent = 0
    deployment.updated_at = now
    db.add(
        DeploymentRevision(
            deployment_id=deployment.id,
            model_version_id=version.id,
            activated_at=now,
            reason="automated_rollout_promoted",
            created_by=rollout.created_by,
        )
    )
    rollout.status = "promoted"
    rollout.completed_at = now
    db.add(
        DeploymentEvent(
            deployment_id=deployment.id,
            level="info",
            message=f"Progressive rollout passed all stages; model v{version.version} is now champion.",
            details={
                "rollout_id": rollout.id,
                "model_version_id": version.id,
                "evaluation": rollout.last_evaluation,
            },
        )
    )
    project = db.get(Project, deployment.project_id)
    if project is not None:
        record_audit(
            db,
            workspace_id=project.workspace_id,
            project_id=deployment.project_id,
            user_id=rollout.created_by,
            action="deployment.rollout_promoted",
            resource_type="deployment",
            resource_id=deployment.id,
            details={
                "rollout_id": rollout.id,
                "model_version_id": version.id,
                "model_version": version.version,
            },
        )


def advance_rollout(db: Session, rollout: DeploymentRollout) -> bool:
    locked = db.execute(
        select(DeploymentRollout)
        .where(DeploymentRollout.id == rollout.id, DeploymentRollout.status == "running")
        .with_for_update()
    ).scalar_one_or_none()
    if locked is None:
        return False
    rollout = locked
    deployment = db.get(Deployment, rollout.deployment_id)
    if deployment is None or deployment.status != "active":
        return False
    report = _evaluate(db, rollout, deployment)
    rollout.last_evaluation = report
    rollout.last_evaluated_at = datetime.now(UTC)
    if report["decision"] == "rollback":
        deployment.challenger_traffic_percent = 0
        rollout.status = "rolled_back"
        rollout.completed_at = datetime.now(UTC)
        db.add(
            DeploymentEvent(
                deployment_id=deployment.id,
                level="error",
                message=f"Progressive rollout rolled back: {report['reason']}",
                details={"rollout_id": rollout.id, "evaluation": report},
            )
        )
    elif report["decision"] == "advance":
        if rollout.current_step + 1 >= len(rollout.traffic_steps):
            _finish_promotion(db, rollout, deployment)
        else:
            rollout.current_step += 1
            rollout.step_started_at = datetime.now(UTC)
            deployment.challenger_traffic_percent = rollout.traffic_steps[rollout.current_step]
            db.add(
                DeploymentEvent(
                    deployment_id=deployment.id,
                    level="info",
                    message=f"Progressive rollout advanced to {deployment.challenger_traffic_percent}% challenger traffic.",
                    details={"rollout_id": rollout.id, "evaluation": report},
                )
            )
    db.add(rollout)
    db.add(deployment)
    db.commit()
    return True


def advance_active_rollouts(db: Session) -> int:
    rollouts = list(
        db.execute(select(DeploymentRollout).where(DeploymentRollout.status == "running")).scalars()
    )
    advanced = 0
    for rollout in rollouts:
        try:
            advanced += int(advance_rollout(db, rollout))
        except Exception:
            db.rollback()
    return advanced
