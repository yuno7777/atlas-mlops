from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BatchPredictionOut(BaseModel):
    id: str
    deployment_id: str
    model_version_id: str
    status: str
    original_filename: str
    row_count: int
    success_count: int
    failed_count: int
    preview: list[dict[str, Any]] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
