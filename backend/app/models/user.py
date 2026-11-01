from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin, utcnow
from app.models.enums import Role


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    memberships: Mapped[list[WorkspaceMember]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Workspace(Base, UUIDMixin):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), unique=True, index=True, nullable=False)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    owner: Mapped[User] = relationship(foreign_keys=[owner_id])
    members: Mapped[list[WorkspaceMember]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    projects: Mapped[list[Project]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_member_workspace_user"),)

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[str] = mapped_column(String(16), default=Role.MEMBER, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    workspace: Mapped[Workspace] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class Project(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("workspace_id", "slug", name="uq_project_workspace_slug"),)

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    workspace: Mapped[Workspace] = relationship(back_populates="projects")
    datasets: Mapped[list[Dataset]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
