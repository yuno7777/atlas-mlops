from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, status

from app.api.deps import ClientIP, CurrentUser, Database
from app.schemas.modelops import (
    BenchmarkReportResponse,
    PipelineRunCreate,
    PipelineRunResponse,
    PipelineTemplate,
)
from app.services import workflows as workflow_service

router = APIRouter(prefix="/benchmarks", tags=["Benchmarks"])


@router.get("/catalog", response_model=list[PipelineTemplate])
def benchmark_catalog(
    user: CurrentUser,
    problem_type: Literal["classification", "regression", "clustering"] | None = None,
) -> list[dict]:
    return workflow_service.pipeline_templates(problem_type)


@router.post("/run", response_model=PipelineRunResponse, status_code=status.HTTP_202_ACCEPTED)
def run_benchmark(
    payload: PipelineRunCreate,
    db: Database,
    user: CurrentUser,
    ip_address: ClientIP,
) -> PipelineRunResponse:
    return workflow_service.create_pipeline_run(db, user, payload, ip_address)


@router.get("/runs", response_model=list[PipelineRunResponse])
def benchmark_runs(
    project_id: str,
    db: Database,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[PipelineRunResponse]:
    return workflow_service.list_pipeline_runs(db, user, project_id, limit)


@router.get("/results", response_model=list[BenchmarkReportResponse])
def benchmark_results(
    project_id: str,
    db: Database,
    user: CurrentUser,
    limit: int = Query(default=40, ge=1, le=100),
) -> list[BenchmarkReportResponse]:
    return workflow_service.benchmark_reports(db, user, project_id, limit)
