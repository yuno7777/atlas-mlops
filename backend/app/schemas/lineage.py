from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class LineageNode(BaseModel):
    id: str
    kind: Literal["dataset", "training_job", "experiment", "model_version", "deployment"]
    label: str
    subtitle: str | None = None
    status: str | None = None
    href: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class LineageEdge(BaseModel):
    source: str
    target: str
    label: str | None = None


class LineageResponse(BaseModel):
    project_id: str
    nodes: list[LineageNode]
    edges: list[LineageEdge]
