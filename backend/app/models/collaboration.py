from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDMixin, utcnow
from app.models.enums import Role


class WorkspaceInvite(Base, UUIDMixin):
    __tablename__ = "workspace_invites"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_workspace_invite_token"),
        Index("ix_workspace_invites_workspace", "workspace_id", "created_at"),
    )

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), default=Role.MEMBER, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    invited_by: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    workspace: Mapped[Workspace] = relationship()  # noqa: F821
    inviter: Mapped[User] = relationship(foreign_keys=[invited_by])  # noqa: F821
    accepted_user: Mapped[User | None] = relationship(foreign_keys=[accepted_by])  # noqa: F821
