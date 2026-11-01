from __future__ import annotations

import json
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import joblib
from sklearn.pipeline import Pipeline
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    RateLimitedError,
    ServiceUnavailableError,
    ValidationError,
)
from app.core.metrics import PREDICTION_LATENCY, PREDICTIONS
from app.core.rate_limit import rate_limiter
from app.core.security import api_key_matches, generate_request_id
from app.ml.inference import run_predictions, validate_records
from app.models.deployment import Deployment, PredictionLog
from app.models.enums import DeploymentStatus
from app.models.registry import ModelVersion
from app.models.user import User
from app.repositories.deployments import DeploymentRepository
from app.schemas.prediction import (
    FeedbackRequest,
    FeedbackResponse,
    PredictionItem,
    PredictionRequest,
    PredictionResponse,
)
from app.services.access import require_project
from app.services.deployments import authenticate_api_key
from app.services.storage import get_storage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoadedModel:
    pipeline: Pipeline
    reference_profile: dict[str, Any]
    problem_type: str


class ModelCache:
    def __init__(self, max_entries: int = 8, ttl_seconds: int = 300) -> None:
        self.max_entries = max(1, max_entries)
        self.ttl_seconds = max(1, ttl_seconds)
        self._entries: OrderedDict[str, tuple[LoadedModel, float]] = OrderedDict()
        self._lock = threading.RLock()

    @staticmethod
    def _key(version_id: str, artifact_sha256: str) -> str:
        return f"{version_id}:{artifact_sha256}"

    def has_entry(self, version_id: str, artifact_sha256: str) -> bool:
        key = self._key(version_id, artifact_sha256)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False
            if entry[1] < time.monotonic() - self.ttl_seconds:
                self._entries.pop(key, None)
                return False
            return True

    def get_or_load(self, version: ModelVersion) -> LoadedModel:
        key = self._key(version.id, version.artifact_sha256)
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                if entry[1] >= time.monotonic() - self.ttl_seconds:
                    self._entries.move_to_end(key)
                    return entry[0]
                self._entries.pop(key, None)
        loaded = self._load(version)
        with self._lock:
            self._entries[key] = (loaded, time.monotonic())
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
        return loaded

    def _load(self, version: ModelVersion) -> LoadedModel:
        storage = get_storage()
        if not storage.exists(version.artifact_key):
            raise ServiceUnavailableError("The deployed model artifact is unavailable.")
        actual_digest = storage.sha256(version.artifact_key)
        if actual_digest != version.artifact_sha256:
            logger.error(
                "Model artifact digest mismatch",
                extra={"version_id": version.id, "expected": version.artifact_sha256},
            )
            raise ServiceUnavailableError("The deployed model artifact failed an integrity check.")
        try:
            with storage.open_path(version.artifact_key) as path:
                pipeline = joblib.load(path)
        except Exception as exc:
            logger.exception("Failed to load model artifact", extra={"version_id": version.id})
            raise ServiceUnavailableError(
                f"The deployed model could not be loaded: {str(exc).splitlines()[0][:200]}"
            ) from exc
        if not hasattr(pipeline, "predict"):
            raise ServiceUnavailableError("The deployed artifact is not a usable model.")
        reference_profile = version.reference_profile or {}
        problem_type = str(
            reference_profile.get("problem_type")
            or (version.experiment.problem_type if version.experiment else "classification")
        )
        return LoadedModel(
            pipeline=pipeline,
            reference_profile=reference_profile,
            problem_type=problem_type,
        )

    def invalidate_version(self, version_id: str) -> None:
        with self._lock:
            for key in [key for key in self._entries if key.startswith(f"{version_id}:")]:
                self._entries.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._entries)


_model_cache: ModelCache | None = None
_model_cache_lock = threading.Lock()


def get_model_cache() -> ModelCache:
    global _model_cache
    if _model_cache is None:
        with _model_cache_lock:
            if _model_cache is None:
                settings = get_settings()
                _model_cache = ModelCache(
                    settings.model_cache_size, settings.model_cache_ttl_seconds
                )
    return _model_cache


def reset_model_cache() -> None:
    global _model_cache
    with _model_cache_lock:
        if _model_cache is not None:
            _model_cache.clear()
        _model_cache = None


def _features_payload(record: dict[str, Any]) -> dict[str, Any] | None:
    try:
        encoded = json.dumps(record, default=str)
    except (TypeError, ValueError):
        return None
    if len(encoded.encode("utf-8")) > get_settings().prediction_log_max_feature_bytes:
        return None
    return record


def _log_failure(
    db: Session,
    deployment: Deployment,
    request_id: str,
    error: str,
    latency_ms: float,
    record: dict[str, Any] | None = None,
) -> None:
    db.add(
        PredictionLog(
            deployment_id=deployment.id,
            model_version_id=deployment.model_version_id,
            request_id=request_id,
            features=_features_payload(record) if record else None,
            prediction=None,
            status="failed",
            error_message=error[:2000],
            latency_ms=round(latency_ms, 3),
        )
    )
    deployment.last_request_at = datetime.now(UTC)
    db.add(deployment)
    try:
        db.commit()
    except Exception:
        logger.exception("Could not persist failed prediction log")
        db.rollback()
    PREDICTIONS.labels(deployment_id=deployment.id, status="failure").inc()


def resolve_prediction_access(
    db: Session,
    deployment_id: str,
    *,
    api_key: str | None,
    user: User | None,
) -> Deployment:
    if api_key:
        return authenticate_api_key(db, deployment_id, api_key)
    if user is not None:
        deployment = DeploymentRepository(db).get(deployment_id)
        if deployment is None:
            raise NotFoundError("Deployment not found.")
        require_project(db, user, deployment.project_id)
        return deployment
    raise AuthenticationError("Provide an X-API-Key header or a bearer token.")


def predict(
    db: Session,
    deployment: Deployment,
    payload: PredictionRequest,
    *,
    client_ip: str | None,
    request_id: str | None = None,
) -> PredictionResponse:
    settings = get_settings()
    request_id = request_id or generate_request_id()
    started = time.perf_counter()
    limiter_key = f"predict:{deployment.id}:{client_ip or 'unknown'}"
    try:
        rate_limiter.check(
            limiter_key, settings.prediction_rate_limit_per_minute, window_seconds=60
        )
    except RateLimitedError as exc:
        latency_ms = (time.perf_counter() - started) * 1000
        _log_failure(
            db,
            deployment,
            request_id,
            exc.message,
            latency_ms,
            payload.records[0] if payload.records else None,
        )
        raise
    if deployment.status != DeploymentStatus.ACTIVE:
        message = "This deployment is not active. Start it before sending predictions."
        _log_failure(
            db,
            deployment,
            request_id,
            message,
            (time.perf_counter() - started) * 1000,
            payload.records[0] if payload.records else None,
        )
        raise ServiceUnavailableError(message)

    try:
        loaded = get_model_cache().get_or_load(deployment.model_version)
        frame = validate_records(payload.records, loaded.reference_profile)
        raw_predictions = run_predictions(loaded.pipeline, loaded.problem_type, frame)
    except Exception as exc:
        error = (
            exc.message if isinstance(exc, (ValidationError, ServiceUnavailableError)) else str(exc)
        )
        _log_failure(
            db,
            deployment,
            request_id,
            error,
            (time.perf_counter() - started) * 1000,
            payload.records[0] if payload.records else None,
        )
        raise

    latency_ms = (time.perf_counter() - started) * 1000
    now = datetime.now(UTC)
    for record, prediction in zip(payload.records, raw_predictions, strict=True):
        db.add(
            PredictionLog(
                deployment_id=deployment.id,
                model_version_id=deployment.model_version_id,
                request_id=request_id,
                features=_features_payload(record),
                prediction=prediction,
                status="success",
                latency_ms=round(latency_ms, 3),
                created_at=now,
            )
        )
    deployment.last_request_at = now
    db.add(deployment)
    db.commit()
    PREDICTIONS.labels(deployment_id=deployment.id, status="success").inc(len(raw_predictions))
    PREDICTION_LATENCY.labels(deployment_id=deployment.id).observe(latency_ms / 1000)
    warnings: list[str] = []
    dropped = loaded.reference_profile.get("dropped_columns") or []
    if dropped:
        warnings.append(f"Training ignored all-null columns: {', '.join(dropped)}")
    return PredictionResponse(
        request_id=request_id,
        deployment_id=deployment.id,
        model_version_id=deployment.model_version_id,
        model_version=deployment.model_version.version,
        predictions=[
            PredictionItem(
                prediction=item.get("prediction"),
                probabilities=item.get("probabilities"),
            )
            for item in raw_predictions
        ],
        latency_ms=round(latency_ms, 3),
        warnings=warnings,
    )


def _deployment_for_api_key(db: Session, api_key: str) -> Deployment:
    from app.core.security import api_key_prefix

    prefix = api_key_prefix(api_key)
    candidates = list(
        db.execute(select(Deployment).where(Deployment.api_key_prefix == prefix)).scalars().all()
    )
    for deployment in candidates:
        if api_key_matches(api_key, deployment.api_key_hash):
            return deployment
    raise AuthenticationError("Invalid deployment API key.")


def _validate_actual(value: Any, index: int) -> None:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        raise ValidationError(
            "Feedback values must be scalar labels.",
            details=[{"field": f"items[{index}].actual", "message": "Expected a scalar label"}],
        )


def submit_feedback(
    db: Session,
    payload: FeedbackRequest,
    *,
    api_key: str | None,
    user: User | None,
    ip_address: str | None = None,
) -> FeedbackResponse:
    for index, item in enumerate(payload.items):
        _validate_actual(item.actual, index)
    scoped_deployment: Deployment | None = None
    if api_key:
        scoped_deployment = _deployment_for_api_key(db, api_key)
    elif user is None:
        raise AuthenticationError("Provide an X-API-Key header or a bearer token.")

    updated = 0
    already_labeled = 0
    not_found = 0
    now = datetime.now(UTC)
    projects_by_deployment: dict[str, str] = {}
    touched_projects: set[str] = set()
    for item in payload.items:
        log = db.get(PredictionLog, item.prediction_id)
        if log is None:
            not_found += 1
            continue
        deployment = db.get(Deployment, log.deployment_id)
        if deployment is None:
            not_found += 1
            continue
        if api_key:
            if deployment.id != scoped_deployment.id:
                not_found += 1
                continue
        else:
            try:
                require_project(db, user, deployment.project_id, write=True)
            except (NotFoundError, ForbiddenError):
                not_found += 1
                continue
        if log.actual is not None:
            already_labeled += 1
            continue
        log.actual = item.actual
        log.actual_received_at = now
        db.add(log)
        updated += 1
        if deployment.project_id not in projects_by_deployment:
            projects_by_deployment[deployment.project_id] = deployment.id
        touched_projects.add(deployment.project_id)
    if updated:
        from app.models.user import Project
        from app.services.audit import record_audit

        for project_id in touched_projects:
            project = db.get(Project, project_id)
            if project is None:
                continue
            record_audit(
                db,
                workspace_id=project.workspace_id,
                project_id=project.id,
                user_id=user.id if user else None,
                action="predictions.feedback",
                resource_type="deployment",
                resource_id=projects_by_deployment[project_id],
                details={"updated": updated},
                ip_address=ip_address,
            )
        db.commit()
    return FeedbackResponse(updated=updated, already_labeled=already_labeled, not_found=not_found)
