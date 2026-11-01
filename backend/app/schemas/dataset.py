from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, Field


class DatasetColumn(BaseModel):
    name: str
    dtype: str
    kind: str
    nullable: bool
    unique_count: int | None = None
    sample_values: list[Any] = Field(default_factory=list)


class DatasetSummary(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None
    latest_version: int
    version_count: int
    latest_version_id: str | None
    row_count: int | None
    column_count: int | None
    size_bytes: int | None
    created_at: datetime
    updated_at: datetime


class DatasetVersionSummary(BaseModel):
    id: str
    dataset_id: str
    version: int
    status: str
    original_filename: str
    size_bytes: int
    row_count: int
    column_count: int
    created_at: datetime


class DatasetVersionOut(BaseModel):
    id: str
    dataset_id: str
    version: int
    status: str
    original_filename: str
    content_type: str
    size_bytes: int
    row_count: int
    column_count: int
    checksum: str
    created_at: datetime
    schema_columns: list[DatasetColumn] = Field(
        validation_alias=AliasChoices("schema_json", "schema_columns"),
        serialization_alias="schema",
    )
    profile: dict[str, Any] = Field(validation_alias=AliasChoices("profile_json", "profile"))
    validation: dict[str, Any] = Field(
        validation_alias=AliasChoices("validation_json", "validation")
    )

    model_config = {"from_attributes": True, "populate_by_name": True}


class DatasetDetail(BaseModel):
    dataset: DatasetSummary
    latest_version: DatasetVersionOut | None = None
    version_count: int


class PreviewResponse(BaseModel):
    columns: list[DatasetColumn]
    rows: list[dict[str, Any]]
    total_rows: int
    returned: int


class DatasetVersionsResponse(BaseModel):
    items: list[DatasetVersionSummary]
    total: int
