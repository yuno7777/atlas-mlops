from __future__ import annotations

import contextlib
import hashlib
import io
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

import pandas as pd
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    ValidationError,
)
from app.ml.profiling import profile_dataframe, validate_dataset
from app.ml.utils import preview_rows
from app.ml.validation import (
    normalize_extension,
    read_dataframe,
    sanitize_dataframe,
    schema_payload,
    validate_content_type,
)
from app.models.dataset import Dataset, DatasetVersion
from app.models.user import User
from app.repositories.datasets import DatasetRepository
from app.schemas.dataset import (
    DatasetColumn,
    DatasetDetail,
    DatasetSummary,
    DatasetVersionOut,
    DatasetVersionSummary,
    PreviewResponse,
)
from app.services.access import require_project
from app.services.audit import record_audit
from app.services.storage import dataset_key, get_storage

CHUNK = 1024 * 1024


def _safe_filename(filename: str) -> str:
    name = Path(filename.replace("\\", "/")).name
    cleaned = "".join(character for character in name if character.isprintable()).strip()
    return (cleaned or "dataset")[:255]


def _stage_upload(stream: BinaryIO, filename: str, max_bytes: int) -> tuple[Path, str, int]:
    extension, _content_type = normalize_extension(filename)
    digest = hashlib.sha256()
    size = 0
    file_descriptor, temp_name = tempfile.mkstemp(suffix=extension)
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
                        f"File exceeds the {max_bytes // (1024 * 1024)} MB upload limit."
                    )
                digest.update(chunk)
                temp.write(chunk)
        if size == 0:
            raise ValidationError("Uploaded file is empty.")
        return temp_path, digest.hexdigest(), size
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _dataset_summary(dataset: Dataset, versions: list[DatasetVersion]) -> DatasetSummary:
    latest = versions[0] if versions else None
    return DatasetSummary(
        id=dataset.id,
        project_id=dataset.project_id,
        name=dataset.name,
        description=dataset.description,
        latest_version=dataset.latest_version,
        version_count=len(versions),
        latest_version_id=latest.id if latest else None,
        row_count=latest.row_count if latest else None,
        column_count=latest.column_count if latest else None,
        size_bytes=latest.size_bytes if latest else None,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
    )


def _version_out(version: DatasetVersion) -> DatasetVersionOut:
    return DatasetVersionOut(
        id=version.id,
        dataset_id=version.dataset_id,
        version=version.version,
        status=version.status,
        original_filename=version.original_filename,
        content_type=version.content_type,
        size_bytes=version.size_bytes,
        row_count=version.row_count,
        column_count=version.column_count,
        checksum=version.checksum,
        created_at=version.created_at,
        schema_json=version.schema_json,
        profile_json=version.profile_json,
        validation_json=version.validation_json,
    )


def _ingest_version(
    db: Session,
    *,
    dataset: Dataset,
    user: User,
    stream: BinaryIO,
    filename: str,
    content_type: str | None,
    ip_address: str | None,
) -> DatasetVersion:
    settings = get_settings()
    project, role = require_project(db, user, dataset.project_id, write=True)
    validate_content_type(content_type)
    original_filename = _safe_filename(filename)
    extension, canonical_content_type = normalize_extension(original_filename)
    max_bytes = settings.max_upload_mb * 1024 * 1024
    repository = DatasetRepository(db)
    temp_path: Path | None = None
    storage_key: str | None = None
    try:
        temp_path, checksum, size = _stage_upload(stream, original_filename, max_bytes)
        if repository.find_checksum(dataset.id, checksum) is not None:
            raise ConflictError("This exact file has already been uploaded for this dataset.")
        df = read_dataframe(temp_path, original_filename)
        df = sanitize_dataframe(df)
        profile = profile_dataframe(df, settings.max_profile_sample_rows)
        validation = validate_dataset(df, profile, size)
        schema = schema_payload(df)
        preview = {"rows": preview_rows(df, settings.max_preview_rows)}
        version_number = repository.next_version_number(dataset.id)
        storage_key = dataset_key(dataset.id, version_number, checksum, extension)
        get_storage().put_file(storage_key, temp_path)
        version = DatasetVersion(
            dataset_id=dataset.id,
            version=version_number,
            status="ready",
            storage_key=storage_key,
            checksum=checksum,
            size_bytes=size,
            row_count=int(len(df)),
            column_count=int(len(df.columns)),
            original_filename=original_filename,
            content_type=canonical_content_type or (content_type or "application/octet-stream"),
            schema_json=schema,
            profile_json=profile,
            preview_json=preview,
            validation_json=validation,
            created_by=user.id,
        )
        repository.add(version)
        dataset.latest_version = version_number
        dataset.updated_at = version.created_at
        db.add(dataset)
        record_audit(
            db,
            workspace_id=project.workspace_id,
            project_id=project.id,
            user_id=user.id,
            action="dataset.version_uploaded",
            resource_type="dataset_version",
            resource_id=version.id,
            details={
                "dataset": dataset.name,
                "version": version_number,
                "rows": version.row_count,
                "columns": version.column_count,
                "size_bytes": size,
            },
            ip_address=ip_address,
        )
        db.commit()
        return version
    except IntegrityError as exc:
        db.rollback()
        if storage_key:
            get_storage().delete(storage_key)
        raise ConflictError("A concurrent upload created this version; retry the upload.") from exc
    except Exception:
        if storage_key:
            with contextlib.suppress(Exception):
                get_storage().delete(storage_key)
        raise
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def create_dataset(
    db: Session,
    user: User,
    *,
    project_id: str,
    name: str,
    description: str | None,
    stream: BinaryIO,
    filename: str,
    content_type: str | None,
    ip_address: str | None = None,
) -> DatasetVersionOut:
    project, _role = require_project(db, user, project_id, write=True)
    cleaned_name = name.strip()
    if not cleaned_name:
        raise ValidationError("Dataset name is required.")
    repository = DatasetRepository(db)
    if repository.get_by_name(project.id, cleaned_name) is not None:
        raise ConflictError("A dataset with this name already exists in this project.")
    dataset = Dataset(
        project_id=project.id,
        name=cleaned_name[:120],
        description=description.strip() if description else None,
        latest_version=0,
        created_by=user.id,
    )
    repository.add(dataset)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A dataset with this name already exists in this project.") from exc
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="dataset.created",
        resource_type="dataset",
        resource_id=dataset.id,
        details={"name": dataset.name},
        ip_address=ip_address,
    )
    version = _ingest_version(
        db,
        dataset=dataset,
        user=user,
        stream=stream,
        filename=filename,
        content_type=content_type,
        ip_address=ip_address,
    )
    return _version_out(version)


def add_dataset_version(
    db: Session,
    user: User,
    *,
    dataset_id: str,
    stream: BinaryIO,
    filename: str,
    content_type: str | None,
    ip_address: str | None = None,
) -> DatasetVersionOut:
    repository = DatasetRepository(db)
    dataset = repository.get(dataset_id)
    if dataset is None:
        raise NotFoundError("Dataset not found.")
    require_project(db, user, dataset.project_id, write=True)
    version = _ingest_version(
        db,
        dataset=dataset,
        user=user,
        stream=stream,
        filename=filename,
        content_type=content_type,
        ip_address=ip_address,
    )
    return _version_out(version)


def list_datasets(
    db: Session,
    user: User,
    *,
    project_id: str,
    search: str | None,
    page: int,
    page_size: int,
) -> tuple[list[DatasetSummary], int]:
    require_project(db, user, project_id)
    repository = DatasetRepository(db)
    offset = (page - 1) * page_size
    datasets, total = repository.list_for_project(project_id, search, offset, page_size)
    versions = repository.versions_for_datasets([dataset.id for dataset in datasets])
    return [_dataset_summary(dataset, versions.get(dataset.id, [])) for dataset in datasets], total


def get_dataset(db: Session, user: User, dataset_id: str) -> DatasetDetail:
    repository = DatasetRepository(db)
    dataset = repository.get(dataset_id)
    if dataset is None:
        raise NotFoundError("Dataset not found.")
    require_project(db, user, dataset.project_id)
    versions = repository.list_versions(dataset.id)
    latest = versions[0] if versions else None
    return DatasetDetail(
        dataset=_dataset_summary(dataset, versions),
        latest_version=_version_out(latest) if latest else None,
        version_count=len(versions),
    )


def list_dataset_versions(db: Session, user: User, dataset_id: str) -> list[DatasetVersionSummary]:
    repository = DatasetRepository(db)
    dataset = repository.get(dataset_id)
    if dataset is None:
        raise NotFoundError("Dataset not found.")
    require_project(db, user, dataset.project_id)
    versions = repository.list_versions(dataset.id)
    return [
        DatasetVersionSummary(
            id=version.id,
            dataset_id=version.dataset_id,
            version=version.version,
            status=version.status,
            original_filename=version.original_filename,
            size_bytes=version.size_bytes,
            row_count=version.row_count,
            column_count=version.column_count,
            created_at=version.created_at,
        )
        for version in versions
    ]


def _get_version_checked(db: Session, user: User, version_id: str) -> DatasetVersion:
    repository = DatasetRepository(db)
    version = repository.get_version(version_id)
    if version is None:
        raise NotFoundError("Dataset version not found.")
    require_project(db, user, version.dataset.project_id)
    return version


def get_dataset_version(db: Session, user: User, version_id: str) -> DatasetVersionOut:
    return _version_out(_get_version_checked(db, user, version_id))


def get_dataset_version_model(db: Session, user: User, version_id: str) -> DatasetVersion:
    return _get_version_checked(db, user, version_id)


def preview_dataset_version(
    db: Session, user: User, version_id: str, limit: int
) -> PreviewResponse:
    version = _get_version_checked(db, user, version_id)
    rows = (version.preview_json or {}).get("rows", [])
    limit = max(1, min(limit, 100))
    return PreviewResponse(
        columns=[DatasetColumn(**column) for column in version.schema_json],
        rows=rows[:limit],
        total_rows=version.row_count,
        returned=min(limit, len(rows)),
    )


def download_dataset_version(
    db: Session, user: User, version_id: str, ip_address: str | None = None
) -> tuple[DatasetVersion, str, Iterator[bytes]]:
    version = _get_version_checked(db, user, version_id)
    project, _role = require_project(db, user, version.dataset.project_id)
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="dataset.downloaded",
        resource_type="dataset_version",
        resource_id=version.id,
        details={"dataset": version.dataset.name, "version": version.version},
        ip_address=ip_address,
    )
    db.commit()
    storage = get_storage()
    if not storage.exists(version.storage_key):
        raise NotFoundError("The dataset artifact is unavailable.")
    return version, version.content_type, storage.iter_chunks(version.storage_key)


def delete_dataset(db: Session, user: User, dataset_id: str, ip_address: str | None = None) -> None:
    repository = DatasetRepository(db)
    dataset = repository.get(dataset_id)
    if dataset is None:
        raise NotFoundError("Dataset not found.")
    project, _role = require_project(db, user, dataset.project_id, write=True)
    if repository.jobs_referencing(dataset.id) > 0:
        raise ConflictError("This dataset has training jobs and cannot be deleted.")
    if repository.model_versions_referencing(dataset.id) > 0:
        raise ConflictError("This dataset is referenced by registered models.")
    keys = [version.storage_key for version in repository.list_versions(dataset.id)]
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="dataset.deleted",
        resource_type="dataset",
        resource_id=dataset.id,
        details={"name": dataset.name, "versions": len(keys)},
        ip_address=ip_address,
    )
    repository.delete(dataset)
    db.commit()
    storage = get_storage()
    for key in keys:
        with contextlib.suppress(Exception):
            storage.delete(key)


def dataframe_from_stream(stream: BinaryIO, filename: str) -> pd.DataFrame:
    """Test helper for parsing an in-memory upload without persisting it."""
    extension, _ = normalize_extension(filename)
    buffer = io.BytesIO(stream.read())
    with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as temp:
        temp.write(buffer.getvalue())
        path = Path(temp.name)
    try:
        return read_dataframe(path, filename)
    finally:
        path.unlink(missing_ok=True)
