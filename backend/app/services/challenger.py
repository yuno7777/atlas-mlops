from __future__ import annotations

import zlib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.deployment import Deployment, DeploymentRevision, PredictionLog
from app.models.enums import ModelStage, ProblemType
from app.models.modelops import DeploymentRollout
from app.models.registry import ModelVersion
from app.models.user import User
from app.repositories.deployments import DeploymentRepository
from app.schemas.deployment import (
    ChallengerInfoResponse,
    ChallengerTrafficRequest,
    ChallengerUpdateRequest,
    ChallengerVariantStats,
)
from app.services.access import require_project
from app.services.audit import record_audit
from app.services.deployments import _close_active_revisions, _event, _target_version


def _ensure_no_automated_rollout(db: Session, deployment_id: str) -> None:
    active = db.execute(
        select(DeploymentRollout.id).where(
            DeploymentRollout.deployment_id == deployment_id,
            DeploymentRollout.status == "running",
        )
    ).scalar_one_or_none()
    if active:
        raise ConflictError(
            "Cancel the active progressive rollout before changing challenger traffic."
        )


def select_variant(deployment: Deployment, request_id: str) -> tuple[str, ModelVersion]:
    challenger = deployment.challenger_model_version
    traffic = int(deployment.challenger_traffic_percent or 0)
    if challenger is not None and traffic > 0:
        bucket = zlib.crc32(request_id.encode("utf-8")) % 100
        if bucket < traffic:
            return "challenger", challenger
    return "champion", deployment.model_version


def _normalized_label(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("prediction")
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip().lower()


def _accuracy(db: Session, deployment_id: str) -> dict[str, tuple[int, int]]:
    rows = db.execute(
        select(PredictionLog.variant, PredictionLog.prediction, PredictionLog.actual).where(
            PredictionLog.deployment_id == deployment_id,
            PredictionLog.status == "success",
            PredictionLog.actual.is_not(None),
        )
    ).all()
    counts: dict[str, tuple[int, int]] = {}
    for variant, prediction, actual in rows:
        predicted_label = _normalized_label(prediction)
        actual_label = _normalized_label(actual)
        correct, labeled = counts.get(variant, (0, 0))
        labeled += 1
        if predicted_label is not None and predicted_label == actual_label:
            correct += 1
        counts[variant] = (correct, labeled)
    return counts


def _info(db: Session, deployment: Deployment) -> ChallengerInfoResponse:
    champion = deployment.model_version
    challenger = deployment.challenger_model_version
    repository = DeploymentRepository(db)
    overview = {row["model_version_id"]: row for row in repository.variant_overview(deployment.id)}
    accuracy = _accuracy(db, deployment.id)
    problem_type = champion.experiment.problem_type if champion and champion.experiment else None
    version_cache: dict[str, ModelVersion | None] = {}

    def version_for(version_id: str) -> ModelVersion | None:
        if version_id not in version_cache:
            version_cache[version_id] = db.get(ModelVersion, version_id)
        return version_cache[version_id]

    variants: list[ChallengerVariantStats] = []
    configured = [("champion", champion.id if champion else deployment.model_version_id)]
    if challenger is not None and challenger.id != deployment.model_version_id:
        configured.append(("challenger", challenger.id))
    for variant, version_id in configured:
        row = overview.get(version_id, {})
        version = version_for(version_id)
        correct, labeled = accuracy.get(variant, (0, 0))
        variants.append(
            ChallengerVariantStats(
                variant=variant,
                model_version_id=version_id,
                model_version=version.version if version else None,
                algorithm=version.algorithm if version else None,
                predictions=int(row.get("predictions", 0)),
                failures=int(row.get("failures", 0)),
                labeled=labeled or int(row.get("labeled", 0)),
                accuracy=(
                    round(correct / labeled, 4)
                    if labeled and problem_type == ProblemType.CLASSIFICATION
                    else None
                ),
                avg_latency_ms=round(float(row.get("avg_latency_ms", 0.0)), 3),
                last_prediction_at=row.get("last_prediction_at"),
            )
        )
    return ChallengerInfoResponse(
        deployment_id=deployment.id,
        champion_version_id=deployment.model_version_id,
        champion_version=champion.version if champion else 0,
        champion_algorithm=champion.algorithm if champion else "",
        challenger_version_id=(
            challenger.id
            if challenger is not None and challenger.id != deployment.model_version_id
            else None
        ),
        challenger_version=(
            challenger.version
            if challenger is not None and challenger.id != deployment.model_version_id
            else None
        ),
        challenger_algorithm=(
            challenger.algorithm
            if challenger is not None and challenger.id != deployment.model_version_id
            else None
        ),
        traffic_percent=int(deployment.challenger_traffic_percent or 0),
        variants=variants,
    )


def get_challenger(db: Session, user: User, deployment_id: str) -> ChallengerInfoResponse:
    deployment = DeploymentRepository(db).get(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    require_project(db, user, deployment.project_id)
    return _info(db, deployment)


def set_challenger(
    db: Session,
    user: User,
    deployment_id: str,
    payload: ChallengerUpdateRequest,
    ip_address: str | None = None,
) -> ChallengerInfoResponse:
    deployment = DeploymentRepository(db).get(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    project, _role = require_project(db, user, deployment.project_id, write=True)
    _ensure_no_automated_rollout(db, deployment.id)
    if payload.model_version_id == deployment.model_version_id:
        raise ConflictError("The champion cannot also be the challenger.")
    version = _target_version(db, deployment.project_id, payload.model_version_id)
    if version.registered_model_id != deployment.registered_model_id:
        raise ConflictError("The challenger must belong to the same registered model.")
    if version.stage == ModelStage.ARCHIVED:
        raise ConflictError("Archived model versions cannot receive traffic.")
    deployment.challenger_model_version_id = version.id
    deployment.challenger_traffic_percent = payload.traffic_percent
    deployment.updated_at = datetime.now(UTC)
    _event(
        db,
        deployment,
        (
            f"Challenger {version.registered_model.name} v{version.version} receives "
            f"{payload.traffic_percent}% of prediction traffic."
        ),
        details={"model_version_id": version.id, "traffic_percent": payload.traffic_percent},
    )
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="deployment.challenger_configured",
        resource_type="deployment",
        resource_id=deployment.id,
        details={"model_version_id": version.id, "traffic_percent": payload.traffic_percent},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(deployment)
    return _info(db, deployment)


def update_traffic(
    db: Session,
    user: User,
    deployment_id: str,
    payload: ChallengerTrafficRequest,
    ip_address: str | None = None,
) -> ChallengerInfoResponse:
    deployment = DeploymentRepository(db).get(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    project, _role = require_project(db, user, deployment.project_id, write=True)
    _ensure_no_automated_rollout(db, deployment.id)
    if deployment.challenger_model_version_id is None:
        raise ConflictError("This deployment has no challenger configured.")
    deployment.challenger_traffic_percent = payload.traffic_percent
    deployment.updated_at = datetime.now(UTC)
    _event(
        db,
        deployment,
        f"Challenger traffic updated to {payload.traffic_percent}%.",
        details={"traffic_percent": payload.traffic_percent},
    )
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="deployment.challenger_traffic_updated",
        resource_type="deployment",
        resource_id=deployment.id,
        details={"traffic_percent": payload.traffic_percent},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(deployment)
    return _info(db, deployment)


def clear_challenger(
    db: Session,
    user: User,
    deployment_id: str,
    ip_address: str | None = None,
    *,
    reason: str = "rejected",
) -> ChallengerInfoResponse:
    deployment = DeploymentRepository(db).get(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    project, _role = require_project(db, user, deployment.project_id, write=True)
    _ensure_no_automated_rollout(db, deployment.id)
    if deployment.challenger_model_version_id is None:
        raise ConflictError("This deployment has no challenger configured.")
    challenger = deployment.challenger_model_version
    deployment.challenger_model_version_id = None
    deployment.challenger_traffic_percent = 0
    deployment.updated_at = datetime.now(UTC)
    _event(
        db,
        deployment,
        (
            f"Challenger {challenger.registered_model.name} v{challenger.version} "
            f"{reason}; all traffic returns to the champion."
        ),
        level="warning",
        details={"model_version_id": challenger.id, "reason": reason},
    )
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="deployment.challenger_cleared",
        resource_type="deployment",
        resource_id=deployment.id,
        details={"model_version_id": challenger.id, "reason": reason},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(deployment)
    return _info(db, deployment)


def promote_challenger(
    db: Session,
    user: User,
    deployment_id: str,
    ip_address: str | None = None,
) -> ChallengerInfoResponse:
    deployment = DeploymentRepository(db).get_detail(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    project, _role = require_project(db, user, deployment.project_id, write=True)
    _ensure_no_automated_rollout(db, deployment.id)
    if deployment.challenger_model_version_id is None:
        raise ConflictError("This deployment has no challenger configured.")
    version = _target_version(db, deployment.project_id, deployment.challenger_model_version_id)
    now = datetime.now(UTC)
    _close_active_revisions(deployment, now)
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
            reason="challenger_promoted",
            created_by=user.id,
        )
    )
    _event(
        db,
        deployment,
        (
            f"Challenger {version.registered_model.name} v{version.version} promoted to champion; "
            "traffic split cleared."
        ),
        details={"model_version_id": version.id},
    )
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="deployment.challenger_promoted",
        resource_type="deployment",
        resource_id=deployment.id,
        details={"model_version_id": version.id, "model_version": version.version},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(deployment)
    return _info(db, deployment)
