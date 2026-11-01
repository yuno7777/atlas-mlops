from __future__ import annotations

from fastapi import APIRouter, Response

from app.api.deps import (
    ApiKey,
    ClientIP,
    Database,
    OptionalUser,
)
from app.schemas.prediction import (
    FeedbackRequest,
    FeedbackResponse,
    PredictionRequest,
    PredictionResponse,
)
from app.services import predictions as prediction_service

router = APIRouter(prefix="/predictions", tags=["Predictions"])


@router.post("/feedback", response_model=FeedbackResponse)
def submit_feedback(
    payload: FeedbackRequest,
    db: Database,
    user: OptionalUser,
    api_key: ApiKey,
    ip_address: ClientIP,
) -> FeedbackResponse:
    return prediction_service.submit_feedback(
        db, payload, api_key=api_key, user=user, ip_address=ip_address
    )


@router.post("/{deployment_id}", response_model=PredictionResponse)
def predict(
    deployment_id: str,
    payload: PredictionRequest,
    db: Database,
    user: OptionalUser,
    api_key: ApiKey,
    ip_address: ClientIP,
    response: Response,
) -> PredictionResponse:
    deployment = prediction_service.resolve_prediction_access(
        db, deployment_id, api_key=api_key, user=user
    )
    result = prediction_service.predict(db, deployment, payload, client_ip=ip_address)
    response.headers["X-Request-ID"] = result.request_id
    return result
