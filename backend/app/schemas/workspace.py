from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class WorkspaceOut(BaseModel):
    id: str
    name: str
    slug: str
    role: str
    created_at: datetime


class MemberOut(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: str
    joined_at: datetime


class ProjectOut(BaseModel):
    id: str
    workspace_id: str
    name: str
    slug: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Project name is required")
        return value


class AuditEventOut(BaseModel):
    id: int
    workspace_id: str | None = None
    project_id: str | None = None
    action: str
    resource_type: str
    resource_id: str | None
    details: dict
    user_email: str | None
    ip_address: str | None = None
    created_at: datetime


class InviteCreateRequest(BaseModel):
    email: EmailStr
    role: Literal["admin", "member", "viewer"] = "member"


class InviteOut(BaseModel):
    id: str
    workspace_id: str
    email: str
    role: str
    status: str
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    invited_by_email: str | None = None


class InviteCreated(InviteOut):
    token: str
    invite_url: str


class MemberRoleUpdateRequest(BaseModel):
    role: Literal["admin", "member", "viewer"]


class AuditEventPage(BaseModel):
    items: list[AuditEventOut]
    total: int
    offset: int
    limit: int
