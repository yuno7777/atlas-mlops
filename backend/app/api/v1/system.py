from __future__ import annotations

import urllib.request
from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.schemas.common import HealthResponse, SystemInfoResponse
from app.schemas.modelops import SLOSnapshot
from app.services.slo import system_slo_snapshot

router = APIRouter(tags=["System"])


def _mlflow_reachable() -> bool:
    settings = get_settings()
    if not settings.mlflow_enabled:
        return False
    uri = settings.mlflow_tracking_uri
    if uri.startswith(("http://", "https://")):
        try:
            with urllib.request.urlopen(  # noqa: S310 - scheme is validated above
                f"{uri.rstrip('/')}/health", timeout=2
            ) as response:
                return 200 <= response.status < 300
        except Exception:
            return False
    try:
        import mlflow

        mlflow.set_tracking_uri(uri)
        mlflow.search_experiments(max_results=1)
        return True
    except Exception:
        return False


@router.get("/health", response_model=HealthResponse)
def api_health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", version=settings.version, environment=settings.environment)


@router.get("/system/info", response_model=SystemInfoResponse)
def system_info(user: CurrentUser) -> SystemInfoResponse:
    settings = get_settings()
    database = "sqlite" if settings.is_sqlite else "postgresql"
    return SystemInfoResponse(
        version=settings.version,
        environment=settings.environment,
        execution_mode=settings.job_execution_mode,
        storage_backend=settings.storage_backend,
        mlflow_enabled=settings.mlflow_enabled,
        mlflow_tracking_uri=settings.mlflow_tracking_uri,
        mlflow_reachable=_mlflow_reachable(),
        database=database,
        monitoring_scheduler=settings.enable_monitoring_scheduler,
        timestamp=datetime.now(UTC),
    )


@router.get("/system/slo", response_model=SLOSnapshot)
def system_slo(user: CurrentUser) -> SLOSnapshot:
    return system_slo_snapshot()
