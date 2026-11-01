from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    datasets,
    deployments,
    experiments,
    predictions,
    registry,
    system,
    training,
    workspaces,
)

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)
api_router.include_router(datasets.router)
api_router.include_router(training.router)
api_router.include_router(experiments.router)
api_router.include_router(registry.router)
api_router.include_router(deployments.router)
api_router.include_router(predictions.router)
