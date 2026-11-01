from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.repositories.audit import AuditRepository


def record_audit(
    db: Session,
    *,
    workspace_id: str,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        workspace_id=workspace_id,
        project_id=project_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
        ip_address=ip_address,
    )
    AuditRepository(db).add(event)
    return event
