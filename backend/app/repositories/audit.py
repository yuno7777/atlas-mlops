from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.models.user import User


class AuditRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, event: AuditEvent) -> None:
        self.db.add(event)
        self.db.flush()

    def list_for_project(self, project_id: str, offset: int, limit: int) -> list[AuditEvent]:
        return list(
            self.db.execute(
                select(AuditEvent)
                .where(AuditEvent.project_id == project_id)
                .order_by(AuditEvent.id.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )

    def list_with_users(
        self, project_id: str, limit: int = 10
    ) -> list[tuple[AuditEvent, str | None]]:
        rows = self.db.execute(
            select(AuditEvent, User.email)
            .outerjoin(User, User.id == AuditEvent.user_id)
            .where(AuditEvent.project_id == project_id)
            .order_by(AuditEvent.id.desc())
            .limit(limit)
        ).all()
        return [(event, email) for event, email in rows]
