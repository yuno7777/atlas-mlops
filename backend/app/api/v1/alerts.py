from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import ClientIP, CurrentUser, Database
from app.schemas.alert import (
    AlertChannelCreateRequest,
    AlertChannelOut,
    AlertChannelTestResponse,
    AlertChannelUpdateRequest,
)
from app.services import alerts as alert_service

router = APIRouter(tags=["Alerts"])


@router.get("/projects/{project_id}/alert-channels", response_model=list[AlertChannelOut])
def list_alert_channels(project_id: str, db: Database, user: CurrentUser) -> list[AlertChannelOut]:
    return alert_service.list_channels(db, user, project_id)


@router.post(
    "/projects/{project_id}/alert-channels",
    response_model=AlertChannelOut,
    status_code=status.HTTP_201_CREATED,
)
def create_alert_channel(
    project_id: str,
    payload: AlertChannelCreateRequest,
    db: Database,
    user: CurrentUser,
    ip_address: ClientIP,
) -> AlertChannelOut:
    return alert_service.create_channel(db, user, project_id, payload, ip_address)


@router.patch(
    "/projects/{project_id}/alert-channels/{channel_id}",
    response_model=AlertChannelOut,
)
def update_alert_channel(
    project_id: str,
    channel_id: str,
    payload: AlertChannelUpdateRequest,
    db: Database,
    user: CurrentUser,
    ip_address: ClientIP,
) -> AlertChannelOut:
    return alert_service.update_channel(db, user, project_id, channel_id, payload, ip_address)


@router.delete(
    "/projects/{project_id}/alert-channels/{channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_alert_channel(
    project_id: str,
    channel_id: str,
    db: Database,
    user: CurrentUser,
    ip_address: ClientIP,
) -> None:
    alert_service.delete_channel(db, user, project_id, channel_id, ip_address)


@router.post(
    "/projects/{project_id}/alert-channels/{channel_id}/test",
    response_model=AlertChannelTestResponse,
)
def test_alert_channel(
    project_id: str, channel_id: str, db: Database, user: CurrentUser
) -> AlertChannelTestResponse:
    return alert_service.test_channel(db, user, project_id, channel_id)
