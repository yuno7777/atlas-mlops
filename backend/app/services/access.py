from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.enums import ROLE_RANK, Role
from app.models.user import Project, User, Workspace
from app.repositories.users import WorkspaceRepository


def require_workspace(
    db: Session, user: User, workspace_id: str, write: bool = False
) -> tuple[Workspace, str]:
    repository = WorkspaceRepository(db)
    membership = repository.get_membership(workspace_id, user.id)
    workspace = repository.get(workspace_id)
    if membership is None or workspace is None:
        raise NotFoundError("Workspace not found.")
    if write and ROLE_RANK.get(membership.role, 0) < ROLE_RANK[Role.MEMBER]:
        raise ForbiddenError("Viewers cannot modify this workspace.")
    return workspace, membership.role


def require_workspace_admin(db: Session, user: User, workspace_id: str) -> tuple[Workspace, str]:
    workspace, role = require_workspace(db, user, workspace_id)
    if ROLE_RANK.get(role, 0) < ROLE_RANK[Role.ADMIN]:
        raise ForbiddenError("Workspace admin access is required.")
    return workspace, role


def require_project(
    db: Session, user: User, project_id: str, write: bool = False
) -> tuple[Project, str]:
    access = WorkspaceRepository(db).get_project_access(project_id, user.id)
    if access is None:
        raise NotFoundError("Project not found.")
    project, role = access
    if write and ROLE_RANK.get(role, 0) < ROLE_RANK[Role.MEMBER]:
        raise ForbiddenError("Viewers cannot modify this project.")
    return project, role
