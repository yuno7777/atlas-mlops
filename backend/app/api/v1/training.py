from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, status

from app.api.deps import ClientIP, CurrentUser, Database, page_payload
from app.ml.algorithms import list_algorithms
from app.schemas.common import Page
from app.schemas.training import (
    AlgorithmOut,
    TrainingJobCreateRequest,
    TrainingJobDetail,
    TrainingJobLogsResponse,
    TrainingJobSummary,
)
from app.services import training as training_service

router = APIRouter(tags=["Training"])


@router.get("/algorithms", response_model=list[AlgorithmOut])
def algorithms(
    problem_type: Literal["classification", "regression", "clustering"] | None = None,
) -> list[AlgorithmOut]:
    return [AlgorithmOut.model_validate(spec.to_dict()) for spec in list_algorithms(problem_type)]


@router.post(
    "/training-jobs",
    response_model=TrainingJobDetail,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_training_job(
    payload: TrainingJobCreateRequest,
    db: Database,
    user: CurrentUser,
    ip_address: ClientIP,
) -> TrainingJobDetail:
    return training_service.create_training_job(db, user, payload, ip_address)


@router.get("/training-jobs", response_model=Page[TrainingJobSummary])
def list_training_jobs(
    db: Database,
    user: CurrentUser,
    project_id: str,
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    items, total = training_service.list_training_jobs(
        db,
        user,
        project_id=project_id,
        status=status_filter,
        search=search,
        page=page,
        page_size=page_size,
    )
    return page_payload(items, total, page, page_size)


@router.get("/training-jobs/{job_id}", response_model=TrainingJobDetail)
def get_training_job(job_id: str, db: Database, user: CurrentUser) -> TrainingJobDetail:
    return training_service.get_training_job(db, user, job_id)


@router.get("/training-jobs/{job_id}/logs", response_model=TrainingJobLogsResponse)
def training_logs(
    job_id: str,
    db: Database,
    user: CurrentUser,
    after_id: int | None = Query(default=None, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
) -> TrainingJobLogsResponse:
    return training_service.get_training_logs(db, user, job_id, after_id, limit)


@router.post("/training-jobs/{job_id}/cancel", response_model=TrainingJobDetail)
def cancel_training_job(
    job_id: str, db: Database, user: CurrentUser, ip_address: ClientIP
) -> TrainingJobDetail:
    return training_service.cancel_training_job(db, user, job_id, ip_address)
