from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query, status

from app.api.deps import ClientIP, CurrentUser, Database, page_payload
from app.schemas.common import Page
from app.schemas.deployment import (
    DeploymentCreated,
    DeploymentCreateRequest,
    DeploymentDetail,
    DeploymentEventOut,
    DeploymentHealthResponse,
    DeploymentSummary,
    DeploymentUpdateRequest,
    PredictionLogOut,
    RotateKeyResponse,
)
from app.schemas.monitoring import (
    MonitoringResultOut,
    RetrainComparisonResponse,
    RetrainRequest,
    TimeseriesResponse,
)
from app.schemas.training import TrainingJobDetail
from app.services import deployments as deployment_service
from app.services import monitoring as monitoring_service

router = APIRouter(tags=["Deployments"])


@router.post("/deployments", response_model=DeploymentCreated, status_code=status.HTTP_201_CREATED)
def create_deployment(
    payload: DeploymentCreateRequest,
    db: Database,
    user: CurrentUser,
    ip_address: ClientIP,
) -> DeploymentCreated:
    return deployment_service.create_deployment(db, user, payload, ip_address)


@router.get("/deployments", response_model=Page[DeploymentSummary])
def list_deployments(
    db: Database,
    user: CurrentUser,
    project_id: str,
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    items, total = deployment_service.list_deployments(
        db,
        user,
        project_id=project_id,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return page_payload(items, total, page, page_size)


@router.get("/deployments/{deployment_id}", response_model=DeploymentDetail)
def get_deployment(deployment_id: str, db: Database, user: CurrentUser) -> DeploymentDetail:
    return deployment_service.get_deployment(db, user, deployment_id)


@router.patch("/deployments/{deployment_id}", response_model=DeploymentDetail)
def update_deployment(
    deployment_id: str,
    payload: DeploymentUpdateRequest,
    db: Database,
    user: CurrentUser,
    ip_address: ClientIP,
) -> DeploymentDetail:
    return deployment_service.update_deployment(db, user, deployment_id, payload, ip_address)


@router.post("/deployments/{deployment_id}/stop", response_model=DeploymentDetail)
def stop_deployment(
    deployment_id: str, db: Database, user: CurrentUser, ip_address: ClientIP
) -> DeploymentDetail:
    return deployment_service.stop_deployment(db, user, deployment_id, ip_address)


@router.post("/deployments/{deployment_id}/start", response_model=DeploymentDetail)
def start_deployment(
    deployment_id: str, db: Database, user: CurrentUser, ip_address: ClientIP
) -> DeploymentDetail:
    return deployment_service.start_deployment(db, user, deployment_id, ip_address)


@router.post("/deployments/{deployment_id}/rollback", response_model=DeploymentDetail)
def rollback_deployment(
    deployment_id: str, db: Database, user: CurrentUser, ip_address: ClientIP
) -> DeploymentDetail:
    return deployment_service.rollback_deployment(db, user, deployment_id, ip_address)


@router.post("/deployments/{deployment_id}/rotate-key", response_model=RotateKeyResponse)
def rotate_api_key(
    deployment_id: str, db: Database, user: CurrentUser, ip_address: ClientIP
) -> RotateKeyResponse:
    return deployment_service.rotate_api_key(db, user, deployment_id, ip_address)


@router.get("/deployments/{deployment_id}/health", response_model=DeploymentHealthResponse)
def deployment_health(
    deployment_id: str, db: Database, user: CurrentUser
) -> DeploymentHealthResponse:
    return deployment_service.deployment_health(db, user, deployment_id)


@router.get("/deployments/{deployment_id}/events", response_model=list[DeploymentEventOut])
def deployment_events(
    deployment_id: str, db: Database, user: CurrentUser
) -> list[DeploymentEventOut]:
    return deployment_service.deployment_events(db, user, deployment_id)


@router.get("/deployments/{deployment_id}/predictions", response_model=Page[PredictionLogOut])
def deployment_predictions(
    deployment_id: str,
    db: Database,
    user: CurrentUser,
    status_filter: str | None = Query(default=None, alias="status"),
    start: datetime | None = Query(default=None, alias="from"),
    end: datetime | None = Query(default=None, alias="to"),
    include_features: bool = True,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    items, total = deployment_service.list_prediction_logs(
        db,
        user,
        deployment_id,
        status=status_filter,
        start=start,
        end=end,
        include_features=include_features,
        page=page,
        page_size=page_size,
    )
    return page_payload(items, total, page, page_size)


@router.post(
    "/deployments/{deployment_id}/retrain",
    response_model=TrainingJobDetail,
    status_code=status.HTTP_202_ACCEPTED,
)
def retrain_deployment(
    deployment_id: str,
    payload: RetrainRequest,
    db: Database,
    user: CurrentUser,
    ip_address: ClientIP,
) -> TrainingJobDetail:
    return monitoring_service.retrain_deployment(db, user, deployment_id, payload, ip_address)


@router.get(
    "/deployments/{deployment_id}/retrain/comparison",
    response_model=RetrainComparisonResponse,
)
def retrain_comparison(
    deployment_id: str, db: Database, user: CurrentUser
) -> RetrainComparisonResponse:
    return monitoring_service.retrain_comparison(db, user, deployment_id)


@router.post(
    "/deployments/{deployment_id}/monitoring/run",
    response_model=MonitoringResultOut,
)
def run_monitoring(
    deployment_id: str, db: Database, user: CurrentUser, ip_address: ClientIP
) -> MonitoringResultOut:
    return monitoring_service.run_monitoring(db, user, deployment_id, ip_address)


@router.get(
    "/deployments/{deployment_id}/monitoring/latest",
    response_model=MonitoringResultOut,
)
def latest_monitoring(deployment_id: str, db: Database, user: CurrentUser) -> MonitoringResultOut:
    return monitoring_service.latest_monitoring(db, user, deployment_id)


@router.get(
    "/deployments/{deployment_id}/monitoring/results",
    response_model=Page[MonitoringResultOut],
)
def list_monitoring(
    deployment_id: str,
    db: Database,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    items, total = monitoring_service.list_monitoring(
        db, user, deployment_id, page=page, page_size=page_size
    )
    return page_payload(items, total, page, page_size)


@router.get(
    "/deployments/{deployment_id}/monitoring/timeseries",
    response_model=TimeseriesResponse,
)
def monitoring_timeseries(
    deployment_id: str,
    db: Database,
    user: CurrentUser,
    hours: int = Query(default=24, ge=1, le=168),
) -> TimeseriesResponse:
    return monitoring_service.monitoring_timeseries(db, user, deployment_id, hours)
