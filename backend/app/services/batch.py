from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    NotFoundError,
    PayloadTooLargeError,
    ServiceUnavailableError,
    ValidationError,
)
from app.ml.inference import run_predictions, validate_records
from app.ml.utils import preview_rows
from app.models.batch import BatchPrediction
from app.models.enums import DeploymentStatus
from app.models.user import User
from app.repositories.batch import BatchPredictionRepository
from app.repositories.deployments import DeploymentRepository
from app.schemas.batch import BatchPredictionOut
from app.services.access import require_project
from app.services.audit import record_audit
from app.services.predictions import get_model_cache
from app.services.storage import get_storage

BATCH_MAX_ROWS = 10_000
CHUNK = 1024 * 1024


def batch_key(deployment_id: str, batch_id: str) -> str:
    return f"batch/{deployment_id}/{batch_id}.csv"


def _safe_filename(filename: str) -> str:
    name = Path(filename.replace("\\", "/")).name
    cleaned = "".join(character for character in name if character.isprintable()).strip()
    return (cleaned or "batch.csv")[:255]


def _batch_out(batch: BatchPrediction) -> BatchPredictionOut:
    return BatchPredictionOut(
        id=batch.id,
        deployment_id=batch.deployment_id,
        model_version_id=batch.model_version_id,
        status=batch.status,
        original_filename=batch.original_filename,
        row_count=batch.row_count,
        success_count=batch.success_count,
        failed_count=batch.failed_count,
        preview=batch.preview or [],
        columns=batch.columns or [],
        error_message=batch.error_message,
        created_at=batch.created_at,
        completed_at=batch.completed_at,
    )


def _read_upload(stream: BinaryIO, filename: str) -> pd.DataFrame:
    settings = get_settings()
    if Path(filename).suffix.lower() not in {".csv", ".txt"}:
        raise ValidationError("Batch uploads must be CSV files.", code="invalid_batch_file")
    max_bytes = settings.max_upload_mb * 1024 * 1024
    digest = hashlib.sha256()
    size = 0
    file_descriptor, temp_name = tempfile.mkstemp(suffix=".csv")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(file_descriptor, "wb") as temp:
            while True:
                chunk = stream.read(CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise PayloadTooLargeError(
                        f"File exceeds the {settings.max_upload_mb} MB upload limit."
                    )
                digest.update(chunk)
                temp.write(chunk)
        if size == 0:
            raise ValidationError("Uploaded file is empty.")
        try:
            frame = pd.read_csv(temp_path)
        except Exception as exc:
            raise ValidationError(
                f"The CSV could not be parsed: {str(exc).splitlines()[0][:250]}"
            ) from exc
        return frame
    finally:
        temp_path.unlink(missing_ok=True)


def _model_frame(
    frame: pd.DataFrame, reference_profile: dict, target_column: str | None
) -> tuple[pd.DataFrame, list[dict]]:
    features = reference_profile.get("schema", {}).get("features", [])
    feature_names = [feature["name"] for feature in features]
    working = frame.copy()
    if target_column and target_column in working.columns and target_column not in feature_names:
        working = working.drop(columns=[target_column])
    if working.empty:
        raise ValidationError("The uploaded CSV contains no rows.")
    if len(working.index) > BATCH_MAX_ROWS:
        raise ValidationError(
            f"Batch uploads are limited to {BATCH_MAX_ROWS:,} rows.",
            code="batch_too_large",
        )
    records = preview_rows(working, len(working.index))
    validated = validate_records(records, reference_profile)
    return validated, records


def _write_results(
    original: list[dict],
    predictions: list[dict],
) -> tuple[bytes, list[dict], list[str]]:
    output_rows: list[dict] = []
    for record, prediction in zip(original, predictions, strict=True):
        row = dict(record)
        row["prediction"] = prediction.get("prediction")
        probabilities = prediction.get("probabilities")
        row["probabilities"] = json.dumps(probabilities, sort_keys=True) if probabilities else ""
        output_rows.append(row)
    columns = list(output_rows[0].keys()) if output_rows else ["prediction"]
    frame = pd.DataFrame(output_rows, columns=columns)
    csv_bytes = frame.to_csv(index=False).encode("utf-8")
    return csv_bytes, output_rows, columns


def create_batch_prediction(
    db: Session,
    user: User,
    deployment_id: str,
    stream: BinaryIO,
    filename: str,
    ip_address: str | None = None,
) -> BatchPredictionOut:
    deployment = DeploymentRepository(db).get(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    project, _role = require_project(db, user, deployment.project_id, write=True)
    if deployment.status != DeploymentStatus.ACTIVE:
        raise ServiceUnavailableError(
            "This deployment is not active. Start it before running batch predictions."
        )
    frame = _read_upload(stream, filename)
    repository = BatchPredictionRepository(db)
    batch = BatchPrediction(
        deployment_id=deployment.id,
        model_version_id=deployment.model_version_id,
        status="processing",
        original_filename=_safe_filename(filename),
        row_count=len(frame.index),
        created_by=user.id,
        preview=[],
        columns=[],
    )
    repository.add(batch)
    db.commit()
    try:
        version = deployment.model_version
        experiment = version.experiment
        target_column = experiment.job.target_column if experiment and experiment.job else None
        loaded = get_model_cache().get_or_load(version)
        model_frame, original = _model_frame(frame, loaded.reference_profile, target_column)
        predictions = run_predictions(loaded.pipeline, loaded.problem_type, model_frame)
        csv_bytes, output_rows, columns = _write_results(original, predictions)
        key = batch_key(deployment.id, batch.id)
        get_storage().put_bytes(key, csv_bytes)
        now = datetime.now(UTC)
        batch.status = "completed"
        batch.row_count = len(output_rows)
        batch.success_count = len(output_rows)
        batch.failed_count = 0
        batch.columns = columns
        batch.preview = output_rows[:20]
        batch.result_key = key
        batch.completed_at = now
        record_audit(
            db,
            workspace_id=project.workspace_id,
            project_id=project.id,
            user_id=user.id,
            action="deployment.batch_prediction",
            resource_type="deployment",
            resource_id=deployment.id,
            details={"batch_id": batch.id, "rows": len(output_rows)},
            ip_address=ip_address,
        )
        db.commit()
        db.refresh(batch)
        return _batch_out(batch)
    except Exception as exc:
        batch.status = "failed"
        batch.error_message = str(exc)[:2000]
        batch.completed_at = datetime.now(UTC)
        db.commit()
        raise


def list_batch_predictions(
    db: Session, user: User, deployment_id: str, limit: int = 25
) -> list[BatchPredictionOut]:
    deployment = DeploymentRepository(db).get(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    require_project(db, user, deployment.project_id)
    batches = BatchPredictionRepository(db).list_for_deployment(deployment_id, limit)
    return [_batch_out(batch) for batch in batches]


def get_batch_prediction(
    db: Session, user: User, deployment_id: str, batch_id: str
) -> BatchPredictionOut:
    deployment = DeploymentRepository(db).get(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    require_project(db, user, deployment.project_id)
    batch = BatchPredictionRepository(db).get(batch_id)
    if batch is None or batch.deployment_id != deployment.id:
        raise NotFoundError("Batch prediction not found.")
    return _batch_out(batch)


def batch_download(
    db: Session, user: User, deployment_id: str, batch_id: str
) -> tuple[BatchPrediction, bytes]:
    deployment = DeploymentRepository(db).get(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    require_project(db, user, deployment.project_id)
    batch = BatchPredictionRepository(db).get(batch_id)
    if batch is None or batch.deployment_id != deployment.id:
        raise NotFoundError("Batch prediction not found.")
    if not batch.result_key:
        raise NotFoundError("This batch has no result file.")
    return batch, get_storage().read_bytes(batch.result_key)
