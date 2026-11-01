from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, status

from app.api.deps import ClientIP, CurrentUser, Database
from app.schemas.modelops import PipelineRunCreate, PipelineRunResponse, PipelineTemplate
from app.services import workflows as workflow_service

router = APIRouter(prefix="/workflows", tags=["Pipeline workflows"])


@router.get("/templates", response_model=list[PipelineTemplate])
def list_templates(
    user: CurrentUser,
    problem_type: Literal["classification", "regression", "clustering"] | None = None,
) -> list[dict]:
    return workflow_service.pipeline_templates(problem_type)


@router.post("/runs", response_model=PipelineRunResponse, status_code=status.HTTP_202_ACCEPTED)
def create_workflow_run(
    payload: PipelineRunCreate,
    db: Database,
    user: CurrentUser,
    ip_address: ClientIP,
) -> PipelineRunResponse:
    return workflow_service.create_pipeline_run(db, user, payload, ip_address)


@router.get("/runs", response_model=list[PipelineRunResponse])
def list_workflow_runs(
    project_id: str,
    db: Database,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[PipelineRunResponse]:
    return workflow_service.list_pipeline_runs(db, user, project_id, limit)


@router.get("/runs/{run_id}", response_model=PipelineRunResponse)
def get_workflow_run(run_id: str, db: Database, user: CurrentUser) -> PipelineRunResponse:
    return workflow_service.get_pipeline_run(db, user, run_id)


@router.post("/runs/{run_id}/retry", response_model=PipelineRunResponse)
def retry_workflow_run(
    run_id: str,
    db: Database,
    user: CurrentUser,
    ip_address: ClientIP,
) -> PipelineRunResponse:
    return workflow_service.retry_pipeline_run(db, user, run_id, ip_address)
