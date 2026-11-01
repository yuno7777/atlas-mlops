from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, Database, page_payload
from app.schemas.common import Page
from app.schemas.experiment import (
    ExperimentCompareRequest,
    ExperimentCompareResponse,
    ExperimentDetail,
    ExperimentSummary,
)
from app.services import training as training_service

router = APIRouter(prefix="/experiments", tags=["Experiments"])


@router.get("", response_model=Page[ExperimentSummary])
def list_experiments(
    db: Database,
    user: CurrentUser,
    project_id: str,
    dataset_version_id: str | None = None,
    algorithm: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    problem_type: str | None = None,
    training_job_id: str | None = Query(default=None, alias="job_id"),
    search: str | None = None,
    sort: Literal[
        "created_at", "-created_at", "name", "-name", "duration", "-duration"
    ] = "-created_at",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    items, total = training_service.list_experiments(
        db,
        user,
        project_id=project_id,
        dataset_version_id=dataset_version_id,
        algorithm=algorithm,
        status=status_filter,
        problem_type=problem_type,
        job_id=training_job_id,
        search=search,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return page_payload(items, total, page, page_size)


@router.post("/compare", response_model=ExperimentCompareResponse)
def compare_experiments(
    payload: ExperimentCompareRequest, db: Database, user: CurrentUser
) -> ExperimentCompareResponse:
    return training_service.compare_experiments(db, user, payload.experiment_ids)


@router.get("/{experiment_id}", response_model=ExperimentDetail)
def get_experiment(experiment_id: str, db: Database, user: CurrentUser) -> ExperimentDetail:
    return training_service.get_experiment(db, user, experiment_id)
