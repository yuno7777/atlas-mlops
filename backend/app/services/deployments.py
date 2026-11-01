from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.security import (
    api_key_matches,
    api_key_prefix,
    generate_api_key,
    hash_api_key,
)
from app.models.deployment import (
    Deployment,
    DeploymentEvent,
    DeploymentRevision,
    PredictionLog,
)
from app.models.enums import DeploymentStatus, ModelStage
from app.models.registry import ModelVersion
from app.models.user import User
from app.repositories.deployments import DeploymentRepository
from app.repositories.monitoring import MonitoringRepository
from app.repositories.registry import RegistryRepository
from app.schemas.deployment import (
    DeploymentCreated,
    DeploymentCreateRequest,
    DeploymentDetail,
    DeploymentEventOut,
    DeploymentHealthResponse,
    DeploymentRevisionOut,
    DeploymentSummary,
    DeploymentUpdateRequest,
    MonitoringConfig,
    PredictionLogOut,
    RotateKeyResponse,
)
from app.services.access import require_project
from app.services.audit import record_audit
from app.services.storage import get_storage


def _normalize_config(config: dict[str, Any] | None) -> dict[str, Any]:
    return MonitoringConfig(**(config or {})).model_dump()


def _deployment_summary(
    deployment: Deployment, latest_monitoring_status: str | None = None
) -> DeploymentSummary:
    model_version = deployment.model_version
    challenger = deployment.challenger_model_version
    model = deployment.registered_model
    return DeploymentSummary(
        id=deployment.id,
        project_id=deployment.project_id,
        name=deployment.name,
        status=deployment.status,
        registered_model_id=deployment.registered_model_id,
        model_name=model.name if model else "Unknown model",
        model_version_id=deployment.model_version_id,
        model_version=model_version.version if model_version else 0,
        algorithm=model_version.algorithm if model_version else "",
        stage=model_version.stage if model_version else ModelStage.NONE,
        challenger_model_version_id=deployment.challenger_model_version_id,
        challenger_model_version=challenger.version if challenger else None,
        challenger_algorithm=challenger.algorithm if challenger else None,
        challenger_traffic_percent=int(deployment.challenger_traffic_percent or 0),
        api_key_prefix=deployment.api_key_prefix,
        description=deployment.description,
        last_request_at=deployment.last_request_at,
        activated_at=deployment.activated_at,
        stopped_at=deployment.stopped_at,
        created_at=deployment.created_at,
        updated_at=deployment.updated_at,
        latest_monitoring_status=latest_monitoring_status,
        config=MonitoringConfig(**deployment.config),
    )


def _revision_out(revision: DeploymentRevision) -> DeploymentRevisionOut:
    return DeploymentRevisionOut(
        id=revision.id,
        model_version_id=revision.model_version_id,
        version=revision.model_version.version if revision.model_version else None,
        activated_at=revision.activated_at,
        deactivated_at=revision.deactivated_at,
        reason=revision.reason,
    )


def _event_out(event: DeploymentEvent) -> DeploymentEventOut:
    return DeploymentEventOut(
        id=event.id,
        level=event.level,
        message=event.message,
        details=event.details,
        created_at=event.created_at,
    )


def _deployment_detail(
    db: Session, deployment: Deployment, latest_status: str | None = None
) -> DeploymentDetail:
    summary = _deployment_summary(deployment, latest_status)
    version = deployment.model_version
    experiment = version.experiment if version else None
    dataset_version = experiment.dataset_version if experiment else None
    revisions = sorted(
        deployment.revisions, key=lambda revision: revision.activated_at, reverse=True
    )
    events = sorted(deployment.events, key=lambda event: event.id, reverse=True)[:50]
    return DeploymentDetail(
        **summary.model_dump(),
        model_metrics=version.metrics if version else {},
        model_params=version.params if version else {},
        problem_type=experiment.problem_type if experiment else None,
        target_column=experiment.job.target_column if experiment and experiment.job else None,
        dataset_name=(
            dataset_version.dataset.name if dataset_version and dataset_version.dataset else None
        ),
        dataset_version=dataset_version.version if dataset_version else None,
        revisions=[_revision_out(revision) for revision in revisions],
        events=[_event_out(event) for event in events],
        model_version_created_at=version.created_at,
    )


def _event(
    db: Session,
    deployment: Deployment,
    message: str,
    *,
    level: str = "info",
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        DeploymentEvent(
            deployment_id=deployment.id,
            level=level,
            message=message[:2000],
            details=details or {},
        )
    )


def _close_active_revisions(deployment: Deployment, now: datetime) -> None:
    for revision in deployment.revisions:
        if revision.deactivated_at is None:
            revision.deactivated_at = now


def _target_version(
    db: Session, project_id: str, version_id: str, *, allow_archived: bool = False
) -> ModelVersion:
    version = RegistryRepository(db).get_version(version_id)
    if version is None or version.registered_model.project_id != project_id:
        raise NotFoundError("Model version not found.")
    if not allow_archived and version.stage == ModelStage.ARCHIVED:
        raise ConflictError("Archived model versions cannot be deployed.")
    if not get_storage().exists(version.artifact_key):
        raise ConflictError("The model artifact is missing from object storage.")
    return version


def create_deployment(
    db: Session,
    user: User,
    payload: DeploymentCreateRequest,
    ip_address: str | None = None,
) -> DeploymentCreated:
    project, _role = require_project(db, user, payload.project_id, write=True)
    name = " ".join(payload.name.split())
    if not name:
        raise ValidationError("Deployment name cannot be blank.")
    repository = DeploymentRepository(db)
    existing = db.execute(
        select(Deployment).where(
            Deployment.project_id == project.id,
            func.lower(Deployment.name) == name.lower(),
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(f"A deployment named '{name}' already exists.")
    version = _target_version(db, project.id, payload.model_version_id)
    now = datetime.now(UTC)
    api_key = generate_api_key()
    deployment = Deployment(
        project_id=project.id,
        registered_model_id=version.registered_model_id,
        model_version_id=version.id,
        name=name,
        description=payload.description,
        status=DeploymentStatus.ACTIVE,
        api_key_hash=hash_api_key(api_key),
        api_key_prefix=api_key_prefix(api_key),
        config=_normalize_config(payload.config.model_dump() if payload.config else None),
        activated_at=now,
        created_by=user.id,
    )
    db.add(deployment)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(f"A deployment named '{name}' already exists.") from exc
    db.add(
        DeploymentRevision(
            deployment_id=deployment.id,
            model_version_id=version.id,
            activated_at=now,
            reason="initial",
            created_by=user.id,
        )
    )
    _event(
        db,
        deployment,
        f"Deployment created and activated with {version.registered_model.name} v{version.version}.",
        details={"model_version_id": version.id},
    )
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="deployment.created",
        resource_type="deployment",
        resource_id=deployment.id,
        details={
            "name": deployment.name,
            "model_name": version.registered_model.name,
            "model_version": version.version,
        },
        ip_address=ip_address,
    )
    db.commit()
    detail = _deployment_detail(db, repository.get_detail(deployment.id))
    return DeploymentCreated(**detail.model_dump(), api_key=api_key)


def list_deployments(
    db: Session,
    user: User,
    *,
    project_id: str,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[DeploymentSummary], int]:
    require_project(db, user, project_id)
    repository = DeploymentRepository(db)
    deployments, total = repository.list(project_id, status, (page - 1) * page_size, page_size)
    latest = repository.latest_monitoring_for([deployment.id for deployment in deployments])
    return [
        _deployment_summary(
            deployment,
            latest[deployment.id].status if deployment.id in latest else None,
        )
        for deployment in deployments
    ], total


def get_deployment(db: Session, user: User, deployment_id: str) -> DeploymentDetail:
    repository = DeploymentRepository(db)
    deployment = repository.get_detail(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    require_project(db, user, deployment.project_id)
    latest = MonitoringRepository(db).latest(deployment.id)
    return _deployment_detail(db, deployment, latest.status if latest else None)


def update_deployment(
    db: Session,
    user: User,
    deployment_id: str,
    payload: DeploymentUpdateRequest,
    ip_address: str | None = None,
) -> DeploymentDetail:
    repository = DeploymentRepository(db)
    deployment = repository.get_detail(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    project, _role = require_project(db, user, deployment.project_id, write=True)
    now = datetime.now(UTC)
    changed: dict[str, Any] = {}
    if payload.name is not None:
        name = " ".join(payload.name.split())
        if not name:
            raise ValidationError("Deployment name cannot be blank.")
        duplicate = db.execute(
            select(Deployment).where(
                Deployment.project_id == deployment.project_id,
                func.lower(Deployment.name) == name.lower(),
                Deployment.id != deployment.id,
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise ConflictError(f"A deployment named '{name}' already exists.")
        if name != deployment.name:
            changed["name"] = name
            deployment.name = name
    if payload.description is not None and payload.description != deployment.description:
        deployment.description = payload.description
        changed["description"] = "updated"
    if payload.config is not None:
        new_config = payload.config.model_dump()
        if new_config != deployment.config:
            deployment.config = new_config
            changed["config"] = "updated"
    if (
        payload.model_version_id is not None
        and payload.model_version_id != deployment.model_version_id
    ):
        version = _target_version(db, deployment.project_id, payload.model_version_id)
        if deployment.status == DeploymentStatus.ACTIVE:
            _close_active_revisions(deployment, now)
            db.add(
                DeploymentRevision(
                    deployment_id=deployment.id,
                    model_version_id=version.id,
                    activated_at=now,
                    reason="manual",
                    created_by=user.id,
                )
            )
            deployment.activated_at = now
        deployment.model_version_id = version.id
        deployment.registered_model_id = version.registered_model_id
        changed["model_version_id"] = version.id
        _event(
            db,
            deployment,
            f"Model version changed to {version.registered_model.name} v{version.version}.",
            details={"model_version_id": version.id},
        )
    if changed:
        deployment.updated_at = now
        db.add(deployment)
        record_audit(
            db,
            workspace_id=project.workspace_id,
            project_id=project.id,
            user_id=user.id,
            action="deployment.updated",
            resource_type="deployment",
            resource_id=deployment.id,
            details=changed,
            ip_address=ip_address,
        )
        db.commit()
    return get_deployment(db, user, deployment.id)


def stop_deployment(
    db: Session, user: User, deployment_id: str, ip_address: str | None = None
) -> DeploymentDetail:
    repository = DeploymentRepository(db)
    deployment = repository.get(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    project, _role = require_project(db, user, deployment.project_id, write=True)
    if deployment.status == DeploymentStatus.STOPPED:
        raise ConflictError("This deployment is already stopped.")
    now = datetime.now(UTC)
    deployment.status = DeploymentStatus.STOPPED
    deployment.stopped_at = now
    deployment.updated_at = now
    _close_active_revisions(deployment, now)
    _event(db, deployment, "Deployment stopped; prediction traffic is disabled.", level="warning")
    db.add(deployment)
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="deployment.stopped",
        resource_type="deployment",
        resource_id=deployment.id,
        ip_address=ip_address,
    )
    db.commit()
    return get_deployment(db, user, deployment.id)


def start_deployment(
    db: Session, user: User, deployment_id: str, ip_address: str | None = None
) -> DeploymentDetail:
    repository = DeploymentRepository(db)
    deployment = repository.get_detail(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    project, _role = require_project(db, user, deployment.project_id, write=True)
    if deployment.status == DeploymentStatus.ACTIVE:
        raise ConflictError("This deployment is already active.")
    version = _target_version(db, deployment.project_id, deployment.model_version_id)
    now = datetime.now(UTC)
    deployment.status = DeploymentStatus.ACTIVE
    deployment.activated_at = now
    deployment.stopped_at = None
    deployment.updated_at = now
    db.add(
        DeploymentRevision(
            deployment_id=deployment.id,
            model_version_id=version.id,
            activated_at=now,
            reason="manual",
            created_by=user.id,
        )
    )
    _event(
        db,
        deployment,
        f"Deployment started with {version.registered_model.name} v{version.version}.",
    )
    db.add(deployment)
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="deployment.started",
        resource_type="deployment",
        resource_id=deployment.id,
        ip_address=ip_address,
    )
    db.commit()
    return get_deployment(db, user, deployment.id)


def rollback_deployment(
    db: Session, user: User, deployment_id: str, ip_address: str | None = None
) -> DeploymentDetail:
    repository = DeploymentRepository(db)
    deployment = repository.get_detail(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    project, _role = require_project(db, user, deployment.project_id, write=True)
    current_revision = next(
        (revision for revision in deployment.revisions if revision.deactivated_at is None),
        None,
    )
    if current_revision is None:
        current_revision = max(
            deployment.revisions, key=lambda revision: revision.activated_at, default=None
        )
    previous = next(
        (
            revision
            for revision in sorted(
                deployment.revisions, key=lambda revision: revision.activated_at, reverse=True
            )
            if revision is not current_revision
            and revision.model_version_id != deployment.model_version_id
        ),
        None,
    )
    if previous is None:
        raise ConflictError("There is no previous revision to roll back to.")
    version = _target_version(db, deployment.project_id, previous.model_version_id)
    now = datetime.now(UTC)
    _close_active_revisions(deployment, now)
    deployment.model_version_id = version.id
    deployment.registered_model_id = version.registered_model_id
    deployment.status = DeploymentStatus.ACTIVE
    deployment.activated_at = now
    deployment.stopped_at = None
    deployment.updated_at = now
    db.add(
        DeploymentRevision(
            deployment_id=deployment.id,
            model_version_id=version.id,
            activated_at=now,
            reason="rollback",
            created_by=user.id,
        )
    )
    _event(
        db,
        deployment,
        f"Rolled back to {version.registered_model.name} v{version.version}.",
        level="warning",
        details={"model_version_id": version.id},
    )
    db.add(deployment)
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="deployment.rolled_back",
        resource_type="deployment",
        resource_id=deployment.id,
        details={"model_version_id": version.id, "model_version": version.version},
        ip_address=ip_address,
    )
    db.commit()
    return get_deployment(db, user, deployment.id)


def rotate_api_key(
    db: Session, user: User, deployment_id: str, ip_address: str | None = None
) -> RotateKeyResponse:
    repository = DeploymentRepository(db)
    deployment = repository.get(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    project, _role = require_project(db, user, deployment.project_id, write=True)
    api_key = generate_api_key()
    deployment.api_key_hash = hash_api_key(api_key)
    deployment.api_key_prefix = api_key_prefix(api_key)
    deployment.updated_at = datetime.now(UTC)
    _event(
        db,
        deployment,
        "Prediction API key rotated; the previous key is no longer valid.",
        level="warning",
    )
    db.add(deployment)
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="deployment.key_rotated",
        resource_type="deployment",
        resource_id=deployment.id,
        ip_address=ip_address,
    )
    db.commit()
    return RotateKeyResponse(api_key=api_key, api_key_prefix=deployment.api_key_prefix)


def authenticate_api_key(db: Session, deployment_id: str, api_key: str) -> Deployment:
    deployment = DeploymentRepository(db).get(deployment_id)
    if deployment is None or not api_key_matches(api_key, deployment.api_key_hash):
        from app.core.exceptions import AuthenticationError

        raise AuthenticationError("Invalid deployment API key.")
    return deployment


def deployment_events(db: Session, user: User, deployment_id: str) -> list[DeploymentEventOut]:
    repository = DeploymentRepository(db)
    deployment = repository.get(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    require_project(db, user, deployment.project_id)
    return [_event_out(event) for event in repository.events(deployment_id)]


def list_prediction_logs(
    db: Session,
    user: User,
    deployment_id: str,
    *,
    status: str | None,
    start: datetime | None,
    end: datetime | None,
    include_features: bool,
    page: int,
    page_size: int,
) -> tuple[list[PredictionLogOut], int]:
    repository = DeploymentRepository(db)
    deployment = repository.get(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    require_project(db, user, deployment.project_id)
    logs, total = repository.predictions(
        deployment_id, status, start, end, (page - 1) * page_size, page_size
    )
    return [
        PredictionLogOut(
            id=log.id,
            deployment_id=log.deployment_id,
            model_version_id=log.model_version_id,
            request_id=log.request_id,
            features=log.features if include_features else None,
            prediction=log.prediction,
            status=log.status,
            error_message=log.error_message,
            latency_ms=log.latency_ms,
            actual=log.actual,
            actual_received_at=log.actual_received_at,
            created_at=log.created_at,
        )
        for log in logs
    ], total


def deployment_health(db: Session, user: User, deployment_id: str) -> DeploymentHealthResponse:
    repository = DeploymentRepository(db)
    deployment = repository.get(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    require_project(db, user, deployment.project_id)
    storage = get_storage()
    artifact_available = storage.exists(deployment.model_version.artifact_key)
    model_loaded: bool | None = None
    try:
        from app.services.predictions import get_model_cache

        model_loaded = get_model_cache().has_entry(
            deployment.model_version_id, deployment.model_version.artifact_sha256
        )
    except Exception:
        model_loaded = None
    latest = MonitoringRepository(db).latest(deployment.id)
    checks: dict[str, str | bool | None] = {
        "active": deployment.status == DeploymentStatus.ACTIVE,
        "artifact_available": artifact_available,
        "model_loaded": model_loaded,
        "monitoring_status": latest.status if latest else None,
        "last_request_at": (
            deployment.last_request_at.isoformat() if deployment.last_request_at else None
        ),
    }
    healthy = deployment.status == DeploymentStatus.ACTIVE and artifact_available
    return DeploymentHealthResponse(
        deployment_id=deployment.id,
        status=deployment.status,
        healthy=healthy,
        checks=checks,
        checked_at=datetime.now(UTC),
    )


def prediction_response_log(log: PredictionLog, include_features: bool) -> PredictionLogOut:
    return PredictionLogOut(
        id=log.id,
        deployment_id=log.deployment_id,
        model_version_id=log.model_version_id,
        request_id=log.request_id,
        features=log.features if include_features else None,
        prediction=log.prediction,
        status=log.status,
        variant=log.variant,
        error_message=log.error_message,
        latency_ms=log.latency_ms,
        actual=log.actual,
        actual_received_at=log.actual_received_at,
        created_at=log.created_at,
    )
