from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.collaboration import WorkspaceInvite
from app.models.user import Project, User, Workspace, WorkspaceMember


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, user_id: str) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self.db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()

    def add(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user


class WorkspaceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_user(self, user_id: str) -> list[tuple[Workspace, str]]:
        rows = self.db.execute(
            select(Workspace, WorkspaceMember.role)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == user_id)
            .order_by(Workspace.created_at.asc())
        ).all()
        return [(workspace, role) for workspace, role in rows]

    def get_membership(self, workspace_id: str, user_id: str) -> WorkspaceMember | None:
        return self.db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        ).scalar_one_or_none()

    def get(self, workspace_id: str) -> Workspace | None:
        return self.db.get(Workspace, workspace_id)

    def list_members(self, workspace_id: str) -> list[WorkspaceMember]:
        return list(
            self.db.execute(
                select(WorkspaceMember)
                .options(joinedload(WorkspaceMember.user))
                .where(WorkspaceMember.workspace_id == workspace_id)
                .order_by(WorkspaceMember.created_at.asc())
            )
            .scalars()
            .all()
        )

    def list_projects(self, workspace_id: str) -> list[Project]:
        return list(
            self.db.execute(
                select(Project)
                .where(Project.workspace_id == workspace_id)
                .order_by(Project.created_at.asc())
            )
            .scalars()
            .all()
        )

    def get_invite(self, invite_id: str) -> WorkspaceInvite | None:
        return self.db.get(WorkspaceInvite, invite_id)

    def get_invite_by_hash(self, token_hash: str) -> WorkspaceInvite | None:
        return self.db.execute(
            select(WorkspaceInvite).where(WorkspaceInvite.token_hash == token_hash)
        ).scalar_one_or_none()

    def list_invites(self, workspace_id: str) -> list[WorkspaceInvite]:
        return list(
            self.db.execute(
                select(WorkspaceInvite)
                .options(joinedload(WorkspaceInvite.inviter))
                .where(WorkspaceInvite.workspace_id == workspace_id)
                .order_by(WorkspaceInvite.created_at.desc())
            )
            .scalars()
            .all()
        )

    def pending_invites(
        self, workspace_id: str, email: str, now: datetime
    ) -> list[WorkspaceInvite]:
        return list(
            self.db.execute(
                select(WorkspaceInvite).where(
                    WorkspaceInvite.workspace_id == workspace_id,
                    WorkspaceInvite.email == email.lower(),
                    WorkspaceInvite.accepted_at.is_(None),
                    WorkspaceInvite.revoked_at.is_(None),
                    WorkspaceInvite.expires_at > now,
                )
            )
            .scalars()
            .all()
        )

    def add_invite(self, invite: WorkspaceInvite) -> WorkspaceInvite:
        self.db.add(invite)
        self.db.flush()
        return invite

    def get_project(self, project_id: str) -> Project | None:
        return self.db.get(Project, project_id)

    def get_project_access(self, project_id: str, user_id: str) -> tuple[Project, str] | None:
        row = self.db.execute(
            select(Project, WorkspaceMember.role)
            .join(Workspace, Workspace.id == Project.workspace_id)
            .join(
                WorkspaceMember,
                (WorkspaceMember.workspace_id == Workspace.id)
                & (WorkspaceMember.user_id == user_id),
            )
            .where(Project.id == project_id)
        ).first()
        if row is None:
            return None
        return row[0], row[1]

    def slug_exists(self, slug: str) -> bool:
        return (
            self.db.execute(select(Workspace.id).where(Workspace.slug == slug)).first() is not None
        )

    def project_slug_exists(self, workspace_id: str, slug: str) -> bool:
        return (
            self.db.execute(
                select(Project.id).where(Project.workspace_id == workspace_id, Project.slug == slug)
            ).first()
            is not None
        )

    def add(self, entity: object) -> None:
        self.db.add(entity)
        self.db.flush()
