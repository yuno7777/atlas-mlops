from __future__ import annotations

from fastapi import APIRouter, Query, status
from fastapi.responses import StreamingResponse

from app.api.deps import ClientIP, CurrentUser, Database, page_payload
from app.schemas.common import Page
from app.schemas.registry import (
    ModelDetail,
    ModelRegisterRequest,
    ModelSummary,
    ModelVersionRegisterRequest,
    ModelVersionSummary,
    PromoteRequest,
    VersionCompareRequest,
    VersionCompareResponse,
)
from app.services import registry as registry_service

router = APIRouter(tags=["Model registry"])


@router.post("/models", response_model=ModelVersionSummary, status_code=status.HTTP_201_CREATED)
def register_model(
    payload: ModelRegisterRequest,
    db: Database,
    user: CurrentUser,
    ip_address: ClientIP,
) -> ModelVersionSummary:
    return registry_service.register_model(db, user, payload, ip_address)


@router.get("/models", response_model=Page[ModelSummary])
def list_models(
    db: Database,
    user: CurrentUser,
    project_id: str,
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    items, total = registry_service.list_models(
        db, user, project_id=project_id, search=search, page=page, page_size=page_size
    )
    return page_payload(items, total, page, page_size)


@router.get("/models/{model_id}", response_model=ModelDetail)
def get_model(model_id: str, db: Database, user: CurrentUser) -> ModelDetail:
    return registry_service.get_model(db, user, model_id)


@router.get("/models/{model_id}/versions", response_model=list[ModelVersionSummary])
def list_model_versions(
    model_id: str, db: Database, user: CurrentUser
) -> list[ModelVersionSummary]:
    return registry_service.list_versions(db, user, model_id)


@router.post(
    "/models/{model_id}/versions",
    response_model=ModelVersionSummary,
    status_code=status.HTTP_201_CREATED,
)
def register_model_version(
    model_id: str,
    payload: ModelVersionRegisterRequest,
    db: Database,
    user: CurrentUser,
    ip_address: ClientIP,
) -> ModelVersionSummary:
    return registry_service.register_version(
        db,
        user,
        model_id,
        payload.experiment_id,
        payload.description,
        ip_address,
    )


@router.post("/models/{model_id}/versions/compare", response_model=VersionCompareResponse)
def compare_model_versions(
    model_id: str,
    payload: VersionCompareRequest,
    db: Database,
    user: CurrentUser,
) -> VersionCompareResponse:
    return registry_service.compare_versions(db, user, model_id, payload)


@router.get("/model-versions/{version_id}", response_model=ModelVersionSummary)
def get_model_version(version_id: str, db: Database, user: CurrentUser) -> ModelVersionSummary:
    return registry_service.get_version(db, user, version_id)


@router.post("/model-versions/{version_id}/promote", response_model=ModelVersionSummary)
def promote_model_version(
    version_id: str,
    payload: PromoteRequest,
    db: Database,
    user: CurrentUser,
    ip_address: ClientIP,
) -> ModelVersionSummary:
    return registry_service.set_stage(db, user, version_id, payload.stage, ip_address)


@router.post("/model-versions/{version_id}/archive", response_model=ModelVersionSummary)
def archive_model_version(
    version_id: str, db: Database, user: CurrentUser, ip_address: ClientIP
) -> ModelVersionSummary:
    return registry_service.archive_version(db, user, version_id, ip_address)


@router.get("/model-versions/{version_id}/download")
def download_model_version(
    version_id: str, db: Database, user: CurrentUser, ip_address: ClientIP
) -> StreamingResponse:
    filename, chunks = registry_service.prepare_download(db, user, version_id, ip_address)
    return StreamingResponse(
        chunks,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
