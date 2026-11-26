from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.routing import APIRoute
from starlette.types import Message

from app.api.deps import (
    ApiKey,
    ClientIP,
    Database,
    OptionalUser,
)
from app.core.config import get_settings
from app.schemas.prediction import (
    FeedbackRequest,
    FeedbackResponse,
    PredictionRequest,
    PredictionResponse,
)
from app.services import predictions as prediction_service


class PredictionRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def limit_body(request: Request) -> Response:
            size = 0
            limit = get_settings().max_prediction_body_bytes

            async def receive() -> Message:
                nonlocal size
                message = await request.receive()
                if message["type"] == "http.request":
                    size += len(message.get("body", b""))
                    if size > limit:
                        raise HTTPException(413, "Prediction request body is too large.")
                return message

            return await handler(Request(request.scope, receive=receive))

        return limit_body


router = APIRouter(prefix="/predictions", tags=["Predictions"], route_class=PredictionRoute)


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
    request: Request,
) -> PredictionResponse:
    deployment = prediction_service.resolve_prediction_access(
        db, deployment_id, api_key=api_key, user=user
    )
    return prediction_service.predict(
        db, deployment, payload, client_ip=ip_address, inference=request.app.state.inference
    )
