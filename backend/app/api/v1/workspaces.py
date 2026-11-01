from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.deps import ClientIP, CurrentUser, Database
from app.schemas.lineage import LineageResponse
from app.schemas.overview import OverviewResponse
from app.schemas.workspace import (
    AuditEventOut,
    AuditEventPage,
    InviteCreated,
    InviteCreateRequest,
    InviteOut,
    MemberOut,
    MemberRoleUpdateRequest,
    ProjectCreateRequest,
    ProjectOut,
    WorkspaceOut,
)
from app.services import team as team_service
from app.services import users as user_service
from app.services.lineage import project_lineage
from app.services.overview import get_overview

router = APIRouter(tags=["Workspaces and projects"])


@router.get("/workspaces", response_model=list[WorkspaceOut])
def list_workspaces(db: Database, user: CurrentUser) -> list[WorkspaceOut]:
    return user_service.list_workspaces(db, user)


@router.get("/workspaces/{workspace_id}/members", response_model=list[MemberOut])
def list_members(workspace_id: str, db: Database, user: CurrentUser) -> list[MemberOut]:
    return user_service.list_members(db, user, workspace_id)


@router.get("/workspaces/{workspace_id}/invites", response_model=list[InviteOut])
def list_invites(workspace_id: str, db: Database, user: CurrentUser) -> list[InviteOut]:
    return team_service.list_invites(db, user, workspace_id)


@router.post(
    "/workspaces/{workspace_id}/invites",
    response_model=InviteCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_invite(
    workspace_id: str,
    payload: InviteCreateRequest,
    db: Database,
    user: CurrentUser,
    ip_address: ClientIP,
) -> InviteCreated:
    return team_service.create_invite(db, user, workspace_id, payload, ip_address)


@router.delete(
    "/workspaces/{workspace_id}/invites/{invite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_invite(
    workspace_id: str,
    invite_id: str,
    db: Database,
    user: CurrentUser,
    ip_address: ClientIP,
) -> None:
    team_service.revoke_invite(db, user, workspace_id, invite_id, ip_address)


@router.patch(
    "/workspaces/{workspace_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def update_member_role(
    workspace_id: str,
    member_id: str,
    payload: MemberRoleUpdateRequest,
    db: Database,
    user: CurrentUser,
    ip_address: ClientIP,
) -> None:
    team_service.update_member_role(db, user, workspace_id, member_id, payload, ip_address)


@router.delete(
    "/workspaces/{workspace_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_member(
    workspace_id: str,
    member_id: str,
    db: Database,
    user: CurrentUser,
    ip_address: ClientIP,
) -> None:
    team_service.remove_member(db, user, workspace_id, member_id, ip_address)


@router.get("/workspaces/{workspace_id}/audit-events", response_model=AuditEventPage)
def workspace_audit_events(
    workspace_id: str,
    db: Database,
    user: CurrentUser,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    action: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
) -> AuditEventPage:
    events, total = team_service.list_workspace_audit_events(
        db,
        user,
        workspace_id,
        offset=offset,
        limit=limit,
        action=action,
        project_id=project_id,
    )
    return AuditEventPage(items=events, total=total, offset=offset, limit=limit)


@router.get("/invites/{token}", response_model=InviteOut)
def invite_preview(token: str, db: Database, user: CurrentUser) -> InviteOut:
    return team_service.get_invite_preview(db, user, token)


@router.post("/invites/{token}/accept", response_model=InviteOut)
def accept_invite(token: str, db: Database, user: CurrentUser, ip_address: ClientIP) -> InviteOut:
    return team_service.accept_invite(db, user, token, ip_address)


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


@router.get("/projects/{project_id}/lineage", response_model=LineageResponse)
def lineage(project_id: str, db: Database, user: CurrentUser) -> LineageResponse:
    return project_lineage(db, user, project_id)


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
