from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AlertChannelCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["slack", "webhook"] = "webhook"
    target_url: str = Field(min_length=8, max_length=1000)
    secret: str | None = Field(default=None, max_length=255)
    min_status: Literal["warning", "critical"] = "warning"
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Channel name is required")
        return value

    @field_validator("target_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith(("https://", "http://")):
            raise ValueError("Target URL must start with http:// or https://")
        return value


class AlertChannelUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    kind: Literal["slack", "webhook"] | None = None
    target_url: str | None = Field(default=None, min_length=8, max_length=1000)
    secret: str | None = Field(default=None, max_length=255)
    min_status: Literal["warning", "critical"] | None = None
    enabled: bool | None = None

    @field_validator("target_url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value.startswith(("https://", "http://")):
            raise ValueError("Target URL must start with http:// or https://")
        return value


class AlertDeliveryOut(BaseModel):
    id: str
    status: str
    response_code: int | None
    error_message: str | None
    created_at: datetime


class AlertChannelOut(BaseModel):
    id: str
    project_id: str
    name: str
    kind: str
    target_url: str
    min_status: str
    enabled: bool
    has_secret: bool
    created_at: datetime
    updated_at: datetime
    last_delivery_status: str | None = None
    last_delivery_at: datetime | None = None
    recent_deliveries: list[AlertDeliveryOut] = Field(default_factory=list)


class AlertChannelTestResponse(BaseModel):
    ok: bool
    response_code: int | None
    error: str | None
    delivered_at: datetime
