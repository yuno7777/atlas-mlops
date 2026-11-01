from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.deps import ClientIP, CurrentUser, Database
from app.schemas.overview import OverviewResponse
from app.schemas.workspace import (
    AuditEventOut,
    MemberOut,
    ProjectCreateRequest,
    ProjectOut,
    WorkspaceOut,
)
from app.services import users as user_service
from app.services.overview import get_overview

router = APIRouter(tags=["Workspaces and projects"])


@router.get("/workspaces", response_model=list[WorkspaceOut])
def list_workspaces(db: Database, user: CurrentUser) -> list[WorkspaceOut]:
    return user_service.list_workspaces(db, user)


@router.get("/workspaces/{workspace_id}/members", response_model=list[MemberOut])
def list_members(workspace_id: str, db: Database, user: CurrentUser) -> list[MemberOut]:
    return user_service.list_members(db, user, workspace_id)


@router.get("/workspaces/{workspace_id}/projects", response_model=list[ProjectOut])
def list_projects(workspace_id: str, db: Database, user: CurrentUser) -> list[ProjectOut]:
    return user_service.list_projects(db, user, workspace_id)


@router.post(
    "/workspaces/{workspace_id}/projects",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    workspace_id: str,
    payload: ProjectCreateRequest,
    db: Database,
    user: CurrentUser,
    ip_address: ClientIP,
) -> ProjectOut:
    return user_service.create_project(db, user, workspace_id, payload, ip_address)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Database, user: CurrentUser) -> ProjectOut:
    return user_service.get_project(db, user, project_id)


@router.get("/projects/{project_id}/overview", response_model=OverviewResponse)
def project_overview(project_id: str, db: Database, user: CurrentUser) -> OverviewResponse:
    return get_overview(db, user, project_id)


@router.get("/projects/{project_id}/audit-events", response_model=list[AuditEventOut])
def audit_events(
    project_id: str,
    db: Database,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AuditEventOut]:
    return user_service.list_audit_events(db, user, project_id, limit)
