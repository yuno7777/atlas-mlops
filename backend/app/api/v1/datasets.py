from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import (
    ClientIP,
    CurrentUser,
    Database,
    page_payload,
)
from app.schemas.common import Page
from app.schemas.dataset import (
    DatasetDetail,
    DatasetSummary,
    DatasetVersionOut,
    DatasetVersionSummary,
    PreviewResponse,
)
from app.services import datasets as dataset_service

router = APIRouter(tags=["Datasets"])


def _content_disposition(filename: str) -> str:
    fallback = filename.encode("ascii", "ignore").decode("ascii") or "dataset"
    fallback = fallback.replace('"', "")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}"


@router.post("/datasets", response_model=DatasetVersionOut, status_code=status.HTTP_201_CREATED)
def create_dataset(
    db: Database,
    user: CurrentUser,
    ip_address: ClientIP,
    project_id: str = Form(...),
    name: str = Form(..., min_length=1, max_length=120),
    description: str | None = Form(default=None),
    file: UploadFile = File(...),
) -> DatasetVersionOut:
    return dataset_service.create_dataset(
        db,
        user,
        project_id=project_id,
        name=name,
        description=description,
        stream=file.file,
        filename=file.filename or "dataset.csv",
        content_type=file.content_type,
        ip_address=ip_address,
    )


@router.get("/datasets", response_model=Page[DatasetSummary])
def list_datasets(
    db: Database,
    user: CurrentUser,
    project_id: str,
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    items, total = dataset_service.list_datasets(
        db, user, project_id=project_id, search=search, page=page, page_size=page_size
    )
    return page_payload(items, total, page, page_size)


@router.get("/datasets/{dataset_id}", response_model=DatasetDetail)
def get_dataset(dataset_id: str, db: Database, user: CurrentUser) -> DatasetDetail:
    return dataset_service.get_dataset(db, user, dataset_id)


@router.post(
    "/datasets/{dataset_id}/versions",
    response_model=DatasetVersionOut,
    status_code=status.HTTP_201_CREATED,
)
def add_version(
    dataset_id: str,
    db: Database,
    user: CurrentUser,
    ip_address: ClientIP,
    file: UploadFile = File(...),
) -> DatasetVersionOut:
    return dataset_service.add_dataset_version(
        db,
        user,
        dataset_id=dataset_id,
        stream=file.file,
        filename=file.filename or "dataset.csv",
        content_type=file.content_type,
        ip_address=ip_address,
    )


@router.get("/datasets/{dataset_id}/versions", response_model=list[DatasetVersionSummary])
def list_versions(dataset_id: str, db: Database, user: CurrentUser) -> list[DatasetVersionSummary]:
    return dataset_service.list_dataset_versions(db, user, dataset_id)


@router.get("/dataset-versions/{version_id}", response_model=DatasetVersionOut)
def get_version(version_id: str, db: Database, user: CurrentUser) -> DatasetVersionOut:
    return dataset_service.get_dataset_version(db, user, version_id)


@router.get("/dataset-versions/{version_id}/preview", response_model=PreviewResponse)
def preview_version(
    version_id: str,
    db: Database,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
) -> PreviewResponse:
    return dataset_service.preview_dataset_version(db, user, version_id, limit)


@router.get("/dataset-versions/{version_id}/download")
def download_version(
    version_id: str, db: Database, user: CurrentUser, ip_address: ClientIP
) -> StreamingResponse:
    version, media_type, chunks = dataset_service.download_dataset_version(
        db, user, version_id, ip_address
    )
    return StreamingResponse(
        chunks,
        media_type=media_type or "application/octet-stream",
        headers={"Content-Disposition": _content_disposition(version.original_filename)},
    )


@router.delete("/datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(dataset_id: str, db: Database, user: CurrentUser, ip_address: ClientIP) -> None:
    dataset_service.delete_dataset(db, user, dataset_id, ip_address)
