from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.alerting import AlertChannel, AlertDelivery
from app.models.deployment import Deployment
from app.models.monitoring import MonitoringResult
from app.models.user import User
from app.repositories.alerts import AlertRepository
from app.repositories.deployments import DeploymentRepository
from app.schemas.alert import (
    AlertChannelCreateRequest,
    AlertChannelOut,
    AlertChannelTestResponse,
    AlertChannelUpdateRequest,
    AlertDeliveryOut,
)
from app.services.access import require_project
from app.services.audit import record_audit

logger = logging.getLogger(__name__)

STATUS_RANK = {"insufficient_data": 0, "healthy": 1, "warning": 2, "critical": 3}


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _check_target(url: str) -> None:
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValidationError("Invalid alert target URL.") from exc
    if parsed.scheme not in {"https", "http"} or not host or parsed.username is not None:
        raise ValidationError("Alert target must be an HTTP(S) URL without user credentials.")
    settings = get_settings()
    if settings.environment == "production":
        allowlist = {
            host.strip().lower() for host in settings.alert_webhook_allowed_hosts.split(",")
        }
        if parsed.scheme != "https" or port not in {None, 443} or host not in allowlist:
            raise ValidationError("Alert target must use HTTPS on an administrator-approved host.")


def _post_json(
    url: str, payload: dict[str, Any], headers: dict[str, str]
) -> tuple[int | None, str | None]:
    try:
        _check_target(url)
    except ValidationError as exc:
        return None, exc.message
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310 - target validated above
        url,
        data=body,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        opener = urllib.request.build_opener(RejectRedirects())
        with opener.open(request, timeout=5) as response:
            return int(response.status), None
    except urllib.error.HTTPError as exc:
        return int(exc.code), f"HTTP {exc.code}"
    except (OSError, ValueError):
        return None, "Could not reach the alert target."


def _delivery_payload(
    channel: AlertChannel,
    deployment: Deployment,
    result: MonitoringResult,
) -> dict[str, Any]:
    drifted = (result.details or {}).get("drifted_features", [])
    summary = (
        f"{deployment.name}: monitoring status is {result.status} "
        f"(drift share {result.drift_share:.0%}, max PSI {result.psi_max:.2f})."
    )
    if channel.kind == "slack":
        return {
            "text": summary,
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*{summary}*"},
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": (
                                f"Deployment `{deployment.id}` · "
                                f"drifted features: {', '.join(drifted[:8]) or 'none'}"
                            ),
                        }
                    ],
                },
            ],
        }
    return {
        "event": "atlas.monitoring.alert",
        "deployment": {
            "id": deployment.id,
            "name": deployment.name,
            "project_id": deployment.project_id,
        },
        "monitoring_result": {
            "id": result.id,
            "status": result.status,
            "drift_share": result.drift_share,
            "psi_max": result.psi_max,
            "data_drift_detected": result.data_drift_detected,
            "prediction_drift_detected": result.prediction_drift_detected,
            "concept_drift_detected": result.concept_drift_detected,
            "drifted_features": drifted,
            "created_at": result.created_at.isoformat(),
        },
    }


def _signature(secret: str, body: dict[str, Any]) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        json.dumps(body, sort_keys=True).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def deliver(
    db: Session,
    channel: AlertChannel,
    deployment: Deployment,
    result: MonitoringResult,
) -> AlertDelivery:
    payload = _delivery_payload(channel, deployment, result)
    headers: dict[str, str] = {}
    if channel.secret:
        headers["X-Atlas-Signature"] = _signature(channel.secret, payload)
    status_code, error = _post_json(channel.target_url, payload, headers)
    delivery = AlertDelivery(
        channel_id=channel.id,
        deployment_id=deployment.id,
        monitoring_result_id=result.id,
        status="failed" if error and (status_code is None or status_code >= 400) else "sent",
        response_code=status_code,
        error_message=error,
        details={
            "status": result.status,
            "drift_share": result.drift_share,
            "psi_max": result.psi_max,
        },
    )
    AlertRepository(db).add_delivery(delivery)
    return delivery


def dispatch_monitoring_alerts(
    db: Session, deployment: Deployment, result: MonitoringResult
) -> int:
    repository = AlertRepository(db)
    channels = repository.list_enabled_channels(deployment.project_id)
    rank = STATUS_RANK.get(result.status, 0)
    sent = 0
    for channel in channels:
        if rank < STATUS_RANK.get(channel.min_status, 2):
            continue
        try:
            deliver(db, channel, deployment, result)
            sent += 1
        except Exception:
            logger.exception(
                "Alert delivery failed",
                extra={"channel_id": channel.id, "deployment_id": deployment.id},
            )
    return sent


def _channel_out(channel: AlertChannel, deliveries: list[AlertDelivery]) -> AlertChannelOut:
    recent = [
        AlertDeliveryOut(
            id=delivery.id,
            status=delivery.status,
            response_code=delivery.response_code,
            error_message=delivery.error_message,
            created_at=delivery.created_at,
        )
        for delivery in deliveries
    ]
    return AlertChannelOut(
        id=channel.id,
        project_id=channel.project_id,
        name=channel.name,
        kind=channel.kind,
        target_url=channel.target_url,
        min_status=channel.min_status,
        enabled=channel.enabled,
        has_secret=bool(channel.secret),
        created_at=channel.created_at,
        updated_at=channel.updated_at,
        last_delivery_status=recent[0].status if recent else None,
        last_delivery_at=recent[0].created_at if recent else None,
        recent_deliveries=recent,
    )


def list_channels(db: Session, user: User, project_id: str) -> list[AlertChannelOut]:
    require_project(db, user, project_id)
    repository = AlertRepository(db)
    channels = repository.list_channels(project_id)
    deliveries = repository.recent_deliveries([channel.id for channel in channels])
    return [_channel_out(channel, deliveries.get(channel.id, [])) for channel in channels]


def create_channel(
    db: Session,
    user: User,
    project_id: str,
    payload: AlertChannelCreateRequest,
    ip_address: str | None = None,
) -> AlertChannelOut:
    project, _role = require_project(db, user, project_id, write=True)
    _check_target(payload.target_url)
    channel = AlertChannel(
        project_id=project.id,
        name=payload.name,
        kind=payload.kind,
        target_url=payload.target_url,
        secret=payload.secret or None,
        min_status=payload.min_status,
        enabled=payload.enabled,
        created_by=user.id,
    )
    AlertRepository(db).add_channel(channel)
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="alert_channel.created",
        resource_type="alert_channel",
        resource_id=channel.id,
        details={"name": channel.name, "kind": channel.kind, "min_status": channel.min_status},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(channel)
    return _channel_out(channel, [])


def update_channel(
    db: Session,
    user: User,
    project_id: str,
    channel_id: str,
    payload: AlertChannelUpdateRequest,
    ip_address: str | None = None,
) -> AlertChannelOut:
    project, _role = require_project(db, user, project_id, write=True)
    repository = AlertRepository(db)
    channel = repository.get_channel(channel_id)
    if channel is None or channel.project_id != project.id:
        raise NotFoundError("Alert channel not found.")
    updates = payload.model_dump(exclude_unset=True)
    if payload.target_url is not None:
        _check_target(payload.target_url)
    if "secret" in updates:
        channel.secret = updates.pop("secret") or None
    for key, value in updates.items():
        if value is not None:
            setattr(channel, key, value)
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="alert_channel.updated",
        resource_type="alert_channel",
        resource_id=channel.id,
        details={"fields": sorted(updates.keys())},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(channel)
    deliveries = repository.recent_deliveries([channel.id]).get(channel.id, [])
    return _channel_out(channel, deliveries)


def delete_channel(
    db: Session,
    user: User,
    project_id: str,
    channel_id: str,
    ip_address: str | None = None,
) -> None:
    project, _role = require_project(db, user, project_id, write=True)
    repository = AlertRepository(db)
    channel = repository.get_channel(channel_id)
    if channel is None or channel.project_id != project.id:
        raise NotFoundError("Alert channel not found.")
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="alert_channel.deleted",
        resource_type="alert_channel",
        resource_id=channel.id,
        details={"name": channel.name},
        ip_address=ip_address,
    )
    db.delete(channel)
    db.commit()


def test_channel(
    db: Session, user: User, project_id: str, channel_id: str
) -> AlertChannelTestResponse:
    require_project(db, user, project_id, write=True)
    channel = AlertRepository(db).get_channel(channel_id)
    if channel is None or channel.project_id != project_id:
        raise NotFoundError("Alert channel not found.")
    payload = {
        "event": "atlas.alert.test",
        "channel": channel.name,
        "message": "Atlas test notification. Your alert channel is configured correctly.",
        "sent_at": datetime.now(UTC).isoformat(),
    }
    if channel.kind == "slack":
        payload = {"text": payload["message"]}
    headers: dict[str, str] = {}
    if channel.secret:
        headers["X-Atlas-Signature"] = _signature(channel.secret, payload)
    status_code, error = _post_json(channel.target_url, payload, headers)
    return AlertChannelTestResponse(
        ok=error is None and (status_code or 0) < 400,
        response_code=status_code,
        error=error,
        delivered_at=datetime.now(UTC),
    )


def latest_deployment_for_project(db: Session, project_id: str) -> Deployment | None:
    deployments = DeploymentRepository(db).list(project_id)
    return deployments[0] if deployments else None
