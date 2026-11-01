from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.collaboration import WorkspaceInvite
from app.models.enums import Role
from app.models.user import User, WorkspaceMember
from app.repositories.audit import AuditRepository
from app.repositories.users import UserRepository, WorkspaceRepository
from app.schemas.workspace import (
    AuditEventOut,
    InviteCreated,
    InviteCreateRequest,
    InviteOut,
    MemberRoleUpdateRequest,
)
from app.services.access import require_workspace_admin
from app.services.audit import record_audit

INVITE_TTL_DAYS = 7


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _invite_status(invite: WorkspaceInvite, now: datetime) -> str:
    if invite.revoked_at is not None:
        return "revoked"
    if invite.accepted_at is not None:
        return "accepted"
    if _as_utc(invite.expires_at) <= now:
        return "expired"
    return "pending"


def _invite_out(invite: WorkspaceInvite, now: datetime) -> InviteOut:
    return InviteOut(
        id=invite.id,
        workspace_id=invite.workspace_id,
        email=invite.email,
        role=invite.role,
        status=_invite_status(invite, now),
        expires_at=invite.expires_at,
        accepted_at=invite.accepted_at,
        revoked_at=invite.revoked_at,
        created_at=invite.created_at,
        invited_by_email=invite.inviter.email if invite.inviter else None,
    )


def list_invites(db: Session, user: User, workspace_id: str) -> list[InviteOut]:
    require_workspace_admin(db, user, workspace_id)
    invites = WorkspaceRepository(db).list_invites(workspace_id)
    now = datetime.now(UTC)
    return [_invite_out(invite, now) for invite in invites]


def create_invite(
    db: Session,
    user: User,
    workspace_id: str,
    payload: InviteCreateRequest,
    ip_address: str | None = None,
) -> InviteCreated:
    _, actor_role = require_workspace_admin(db, user, workspace_id)
    if payload.role == Role.ADMIN and actor_role != Role.OWNER:
        raise ForbiddenError("Only the workspace owner can invite admins.")
    repository = WorkspaceRepository(db)
    email = str(payload.email).lower().strip()
    existing_user = UserRepository(db).get_by_email(email)
    if existing_user is not None and repository.get_membership(workspace_id, existing_user.id):
        raise ConflictError("This user is already a workspace member.")
    now = datetime.now(UTC)
    for pending in repository.pending_invites(workspace_id, email, now):
        pending.revoked_at = now
    token = secrets.token_urlsafe(32)
    invite = WorkspaceInvite(
        workspace_id=workspace_id,
        email=email,
        role=payload.role,
        token_hash=_hash_token(token),
        invited_by=user.id,
        expires_at=now + timedelta(days=INVITE_TTL_DAYS),
    )
    repository.add_invite(invite)
    record_audit(
        db,
        workspace_id=workspace_id,
        user_id=user.id,
        action="member.invited",
        resource_type="workspace_invite",
        resource_id=invite.id,
        details={"email": email, "role": payload.role},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(invite)
    out = _invite_out(invite, now)
    return InviteCreated(
        **out.model_dump(),
        token=token,
        invite_url=f"/invite/{token}",
    )


def revoke_invite(
    db: Session,
    user: User,
    workspace_id: str,
    invite_id: str,
    ip_address: str | None = None,
) -> None:
    require_workspace_admin(db, user, workspace_id)
    invite = WorkspaceRepository(db).get_invite(invite_id)
    if invite is None or invite.workspace_id != workspace_id:
        raise NotFoundError("Invite not found.")
    if invite.accepted_at is not None or invite.revoked_at is not None:
        raise ConflictError("This invite can no longer be revoked.")
    invite.revoked_at = datetime.now(UTC)
    record_audit(
        db,
        workspace_id=workspace_id,
        user_id=user.id,
        action="member.invite_revoked",
        resource_type="workspace_invite",
        resource_id=invite.id,
        details={"email": invite.email},
        ip_address=ip_address,
    )
    db.commit()


def get_invite_preview(db: Session, user: User, token: str) -> InviteOut:
    repository = WorkspaceRepository(db)
    invite = repository.get_invite_by_hash(_hash_token(token))
    if invite is None:
        raise NotFoundError("Invite not found.")
    now = datetime.now(UTC)
    status = _invite_status(invite, now)
    if status == "expired":
        raise ValidationError("This invite has expired.", code="invite_expired")
    if status == "revoked":
        raise ValidationError("This invite was revoked.", code="invite_revoked")
    if status == "accepted":
        raise ConflictError("This invite has already been accepted.")
    if invite.email != user.email.lower():
        raise ForbiddenError("This invite was issued to a different email address.")
    return _invite_out(invite, now)


def accept_invite(
    db: Session,
    user: User,
    token: str,
    ip_address: str | None = None,
) -> InviteOut:
    repository = WorkspaceRepository(db)
    invite = repository.get_invite_by_hash(_hash_token(token))
    if invite is None:
        raise NotFoundError("Invite not found.")
    now = datetime.now(UTC)
    status = _invite_status(invite, now)
    if status == "expired":
        raise ValidationError("This invite has expired.", code="invite_expired")
    if status == "revoked":
        raise ValidationError("This invite was revoked.", code="invite_revoked")
    if status == "accepted":
        raise ConflictError("This invite has already been accepted.")
    if invite.email != user.email.lower():
        raise ForbiddenError("This invite was issued to a different email address.")
    if repository.get_membership(invite.workspace_id, user.id) is not None:
        raise ConflictError("You are already a member of this workspace.")
    repository.add(
        WorkspaceMember(
            workspace_id=invite.workspace_id,
            user_id=user.id,
            role=invite.role,
        )
    )
    invite.accepted_at = now
    invite.accepted_by = user.id
    record_audit(
        db,
        workspace_id=invite.workspace_id,
        user_id=user.id,
        action="member.joined",
        resource_type="workspace_invite",
        resource_id=invite.id,
        details={"email": user.email, "role": invite.role},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(invite)
    return _invite_out(invite, now)


def update_member_role(
    db: Session,
    user: User,
    workspace_id: str,
    member_id: str,
    payload: MemberRoleUpdateRequest,
    ip_address: str | None = None,
) -> None:
    _, actor_role = require_workspace_admin(db, user, workspace_id)
    repository = WorkspaceRepository(db)
    member = repository.get_membership(workspace_id, member_id)
    if member is None:
        raise NotFoundError("Workspace member not found.")
    if member.role == Role.OWNER:
        raise ForbiddenError("The workspace owner role cannot be changed.")
    if member.user_id == user.id:
        raise ForbiddenError("You cannot change your own workspace role.")
    if payload.role == Role.ADMIN and actor_role != Role.OWNER:
        raise ForbiddenError("Only the workspace owner can grant admin access.")
    member.role = payload.role
    record_audit(
        db,
        workspace_id=workspace_id,
        user_id=user.id,
        action="member.role_updated",
        resource_type="workspace_member",
        resource_id=member.user_id,
        details={"role": payload.role},
        ip_address=ip_address,
    )
    db.commit()


def remove_member(
    db: Session,
    user: User,
    workspace_id: str,
    member_id: str,
    ip_address: str | None = None,
) -> None:
    _, actor_role = require_workspace_admin(db, user, workspace_id)
    repository = WorkspaceRepository(db)
    member = repository.get_membership(workspace_id, member_id)
    if member is None:
        raise NotFoundError("Workspace member not found.")
    if member.role == Role.OWNER:
        raise ForbiddenError("The workspace owner cannot be removed.")
    if member.user_id == user.id:
        raise ForbiddenError("You cannot remove yourself from the workspace.")
    if member.role == Role.ADMIN and actor_role != Role.OWNER:
        raise ForbiddenError("Only the workspace owner can remove an admin.")
    record_audit(
        db,
        workspace_id=workspace_id,
        user_id=user.id,
        action="member.removed",
        resource_type="workspace_member",
        resource_id=member.user_id,
        details={"email": member.user.email if member.user else None},
        ip_address=ip_address,
    )
    db.delete(member)
    db.commit()


def list_workspace_audit_events(
    db: Session,
    user: User,
    workspace_id: str,
    *,
    offset: int = 0,
    limit: int = 50,
    action: str | None = None,
    project_id: str | None = None,
) -> tuple[list[AuditEventOut], int]:
    require_workspace_admin(db, user, workspace_id)
    rows, total = AuditRepository(db).list_for_workspace(
        workspace_id,
        offset=offset,
        limit=limit,
        action=action,
        project_id=project_id,
    )
    events = [
        AuditEventOut(
            id=event.id,
            workspace_id=event.workspace_id,
            project_id=event.project_id,
            action=event.action,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            details=event.details,
            user_email=email,
            ip_address=event.ip_address,
            created_at=event.created_at,
        )
        for event, email in rows
    ]
    return events, total
