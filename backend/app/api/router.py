from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    auth,
    benchmarks,
    datasets,
    deployments,
    experiments,
    predictions,
    registry,
    system,
    training,
    workflows,
    workspaces,
)

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)
api_router.include_router(benchmarks.router)
api_router.include_router(workflows.router)
api_router.include_router(alerts.router)
api_router.include_router(datasets.router)
api_router.include_router(training.router)
api_router.include_router(experiments.router)
api_router.include_router(registry.router)
api_router.include_router(deployments.router)
api_router.include_router(predictions.router)
