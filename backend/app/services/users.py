from __future__ import annotations

import re
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    InvalidCredentialsError,
    NotFoundError,
    ValidationError,
)
from app.core.rate_limit import rate_limiter
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.enums import Role
from app.models.user import Project, User, Workspace, WorkspaceMember
from app.repositories.users import UserRepository, WorkspaceRepository
from app.schemas.auth import RegisterRequest, TokenResponse, UserOut
from app.schemas.workspace import (
    AuditEventOut,
    MemberOut,
    ProjectCreateRequest,
    ProjectOut,
    WorkspaceOut,
)
from app.services.access import require_workspace, require_workspace_admin
from app.services.audit import record_audit


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug or "workspace")[:100]


def _unique_workspace_slug(repository: WorkspaceRepository, base: str) -> str:
    candidate = slugify(base)
    if not repository.slug_exists(candidate):
        return candidate
    return f"{candidate[:88]}-{uuid.uuid4().hex[:8]}"


def _unique_project_slug(repository: WorkspaceRepository, workspace_id: str, base: str) -> str:
    candidate = slugify(base)
    if not repository.project_slug_exists(workspace_id, candidate):
        return candidate
    return f"{candidate[:108]}-{uuid.uuid4().hex[:8]}"


def register_user(
    db: Session, payload: RegisterRequest, ip_address: str | None = None
) -> TokenResponse:
    settings = get_settings()
    if not settings.allow_registration:
        raise AuthenticationError(
            "Self-service registration is disabled.", code="registration_disabled"
        )
    email = payload.email.lower().strip()
    repository = UserRepository(db)
    if repository.get_by_email(email) is not None:
        raise ConflictError("An account with this email already exists.")
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        is_active=True,
    )
    repository.add(user)
    workspace_repository = WorkspaceRepository(db)
    workspace_name = (payload.workspace_name or f"{payload.full_name}'s workspace").strip()
    workspace = Workspace(
        name=workspace_name[:120],
        slug=_unique_workspace_slug(workspace_repository, workspace_name),
        owner_id=user.id,
    )
    workspace_repository.add(workspace)
    workspace_repository.add(
        WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=Role.OWNER)
    )
    project = Project(
        workspace_id=workspace.id,
        name="Default project",
        slug=_unique_project_slug(workspace_repository, workspace.id, "default-project"),
        description="Automatically created workspace project.",
    )
    workspace_repository.add(project)
    record_audit(
        db,
        workspace_id=workspace.id,
        project_id=project.id,
        user_id=user.id,
        action="user.registered",
        resource_type="user",
        resource_id=user.id,
        details={"email": email},
        ip_address=ip_address,
    )
    db.commit()
    token, expires_in = create_access_token(user.id)
    return TokenResponse(
        access_token=token, expires_in=expires_in, user=UserOut.model_validate(user)
    )


def login(db: Session, email: str, password: str, ip_address: str | None = None) -> TokenResponse:
    settings = get_settings()
    normalized = email.lower().strip()
    rate_limiter.check(
        f"login:{ip_address or 'unknown'}:{normalized}",
        settings.login_rate_limit_per_minute * 3,
        window_seconds=300,
    )
    repository = UserRepository(db)
    user = repository.get_by_email(normalized)
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError("Invalid email or password.")
    if not user.is_active:
        raise AuthenticationError("This account is disabled.")
    memberships = WorkspaceRepository(db).list_for_user(user.id)
    if memberships:
        record_audit(
            db,
            workspace_id=memberships[0][0].id,
            user_id=user.id,
            action="user.logged_in",
            resource_type="user",
            resource_id=user.id,
            ip_address=ip_address,
        )
        db.commit()
    token, expires_in = create_access_token(user.id)
    return TokenResponse(
        access_token=token, expires_in=expires_in, user=UserOut.model_validate(user)
    )


def update_profile(db: Session, user: User, full_name: str) -> UserOut:
    cleaned = full_name.strip()
    if not cleaned:
        raise ValidationError("Full name cannot be empty.")
    user.full_name = cleaned
    db.add(user)
    db.commit()
    return UserOut.model_validate(user)


def change_password(db: Session, user: User, current: str, new: str) -> None:
    if not verify_password(current, user.password_hash):
        raise AuthenticationError("Current password is incorrect.", code="invalid_credentials")
    if verify_password(new, user.password_hash):
        raise ValidationError("New password must differ from the current password.")
    user.password_hash = hash_password(new)
    db.add(user)
    db.commit()


def list_workspaces(db: Session, user: User) -> list[WorkspaceOut]:
    rows = WorkspaceRepository(db).list_for_user(user.id)
    return [
        WorkspaceOut(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            role=role,
            created_at=workspace.created_at,
        )
        for workspace, role in rows
    ]


def list_members(db: Session, user: User, workspace_id: str) -> list[MemberOut]:
    require_workspace(db, user, workspace_id)
    members = WorkspaceRepository(db).list_members(workspace_id)
    return [
        MemberOut(
            user_id=member.user_id,
            email=member.user.email,
            full_name=member.user.full_name,
            role=member.role,
            joined_at=member.created_at,
        )
        for member in members
    ]


def list_projects(db: Session, user: User, workspace_id: str) -> list[ProjectOut]:
    require_workspace(db, user, workspace_id)
    projects = WorkspaceRepository(db).list_projects(workspace_id)
    return [ProjectOut.model_validate(project) for project in projects]


def get_project(db: Session, user: User, project_id: str) -> ProjectOut:
    from app.services.access import require_project

    project, _role = require_project(db, user, project_id)
    return ProjectOut.model_validate(project)


def create_project(
    db: Session,
    user: User,
    workspace_id: str,
    payload: ProjectCreateRequest,
    ip_address: str | None = None,
) -> ProjectOut:
    workspace, _role = require_workspace_admin(db, user, workspace_id)
    repository = WorkspaceRepository(db)
    project = Project(
        workspace_id=workspace.id,
        name=payload.name,
        slug=_unique_project_slug(repository, workspace.id, payload.name),
        description=payload.description,
    )
    db.add(project)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A project with this name already exists.") from exc
    record_audit(
        db,
        workspace_id=workspace.id,
        project_id=project.id,
        user_id=user.id,
        action="project.created",
        resource_type="project",
        resource_id=project.id,
        details={"name": project.name},
        ip_address=ip_address,
    )
    db.commit()
    return ProjectOut.model_validate(project)


def list_audit_events(
    db: Session, user: User, project_id: str, limit: int = 50
) -> list[AuditEventOut]:
    from app.repositories.audit import AuditRepository
    from app.services.access import require_project

    require_project(db, user, project_id)
    rows = AuditRepository(db).list_with_users(project_id, limit)
    return [
        AuditEventOut(
            id=event.id,
            action=event.action,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            details=event.details,
            user_email=email,
            created_at=event.created_at,
        )
        for event, email in rows
    ]


def get_user_or_404(db: Session, user_id: str) -> User:
    user = UserRepository(db).get(user_id)
    if user is None:
        raise NotFoundError("User not found.")
    return user
