from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.db.base import new_id
from app.ml.evaluation import METRIC_DIRECTIONS, metric_directions
from app.ml.utils import float_or_none
from app.models.enums import ExperimentStatus, ModelStage, ProblemType
from app.models.registry import ModelVersion, RegisteredModel
from app.models.training import Experiment
from app.models.user import Project, User
from app.repositories.registry import RegistryRepository
from app.repositories.training import ExperimentRepository
from app.schemas.registry import (
    ModelDetail,
    ModelRegisterRequest,
    ModelSummary,
    ModelVersionSummary,
    VersionCompareRequest,
    VersionCompareResponse,
)
from app.services.access import require_project
from app.services.audit import record_audit
from app.services.storage import get_storage, registry_artifact_prefix


def _framework_for(algorithm: str) -> str:
    return "pytorch" if algorithm == "mlp_torch" else "scikit-learn"


def _reference_feature_count(reference_profile: dict[str, Any] | None) -> int:
    if not reference_profile:
        return 0
    features = reference_profile.get("features")
    if isinstance(features, dict):
        return len(features)
    return 0


def _version_summary(
    version: ModelVersion,
    *,
    deployment_count: int = 0,
    problem_type: str | None = None,
) -> ModelVersionSummary:
    experiment = version.experiment
    return ModelVersionSummary(
        id=version.id,
        registered_model_id=version.registered_model_id,
        registered_model_name=(version.registered_model.name if version.registered_model else None),
        version=version.version,
        experiment_id=version.experiment_id,
        dataset_version_id=version.dataset_version_id,
        algorithm=version.algorithm,
        framework=version.framework,
        stage=version.stage,
        metrics=version.metrics,
        params=version.params,
        artifact_sha256=version.artifact_sha256,
        created_at=version.created_at,
        created_by=version.created_by,
        deployment_count=deployment_count,
        problem_type=problem_type or (experiment.problem_type if experiment else None),
        reference_feature_count=_reference_feature_count(version.reference_profile),
    )


def _model_summary(
    model: RegisteredModel, versions: list[ModelVersion] | None = None
) -> ModelSummary:
    items = versions if versions is not None else list(model.versions)
    ordered = sorted(items, key=lambda version: version.version, reverse=True)
    latest = ordered[0] if ordered else None
    production = next(
        (version for version in ordered if version.stage == ModelStage.PRODUCTION), None
    )
    return ModelSummary(
        id=model.id,
        project_id=model.project_id,
        name=model.name,
        description=model.description,
        latest_version=model.latest_version,
        version_count=len(ordered),
        created_at=model.created_at,
        updated_at=model.updated_at,
        latest_stage=latest.stage if latest else None,
        latest_metrics=latest.metrics if latest else None,
        latest_algorithm=latest.algorithm if latest else None,
        production_version=production.version if production else None,
    )


def _normalize_name(name: str) -> str:
    normalized = " ".join(name.split())
    if not normalized:
        raise ValidationError("Model name cannot be blank.")
    if len(normalized) > 120:
        raise ValidationError("Model name must be at most 120 characters.")
    return normalized


def _get_project_for_experiment(db: Session, experiment: Experiment) -> Project:
    project = db.get(Project, experiment.project_id)
    if project is None:
        raise NotFoundError("Project not found.")
    return project


def register_experiment_as_model(
    db: Session,
    *,
    experiment_id: str,
    user_id: str,
    model_name: str,
    description: str | None = None,
    model_id: str | None = None,
    add_to_existing: bool = False,
    commit: bool = True,
    ip_address: str | None = None,
) -> ModelVersion:
    repository = RegistryRepository(db)
    experiment = ExperimentRepository(db).get(experiment_id)
    if experiment is None:
        raise NotFoundError("Experiment not found.")
    if experiment.status != ExperimentStatus.COMPLETED:
        raise ConflictError("Only completed experiments can be registered.")
    if not experiment.artifact_key:
        raise ConflictError("The experiment artifact is not available.")
    storage = get_storage()
    if not storage.exists(experiment.artifact_key):
        raise ConflictError("The experiment artifact is missing from object storage.")
    project = _get_project_for_experiment(db, experiment)
    normalized_name = _normalize_name(model_name)

    if model_id:
        model = repository.get_model(model_id)
        if model is None or model.project_id != experiment.project_id:
            raise NotFoundError("Registered model not found.")
    else:
        model = db.execute(
            select(RegisteredModel).where(
                RegisteredModel.project_id == experiment.project_id,
                func.lower(RegisteredModel.name) == normalized_name.lower(),
            )
        ).scalar_one_or_none()
        if model is not None and not add_to_existing:
            raise ConflictError(
                f"A model named '{model.name}' already exists. Register a new version instead."
            )
    if model is None:
        model = RegisteredModel(
            project_id=experiment.project_id,
            name=normalized_name,
            description=description,
            latest_version=0,
            created_by=user_id,
        )
        db.add(model)
        db.flush()
    duplicate = repository.version_for_experiment(model.id, experiment.id)
    if duplicate is not None:
        raise ConflictError(
            f"This experiment is already registered as version {duplicate.version} of {model.name}."
        )

    next_version = repository.next_version_number(model.id)
    version_id = new_id()
    prefix = f"{registry_artifact_prefix(model.id, next_version)}/{version_id}"
    model_key = f"{prefix}/model.joblib"
    reference_key = f"{prefix}/reference_profile.json"
    copied: list[str] = []
    try:
        with storage.open_path(experiment.artifact_key) as source:
            storage.put_file(model_key, source)
        copied.append(model_key)
        artifact_sha256 = storage.sha256(model_key)
        reference_profile = experiment.reference_profile or {}
        expected_digest = reference_profile.get("provenance", {}).get("model_sha256")
        if expected_digest and artifact_sha256 != expected_digest:
            raise ValidationError("The training artifact failed its integrity check.")
        storage.put_bytes(
            reference_key,
            json.dumps(reference_profile, indent=2).encode("utf-8"),
        )
        copied.append(reference_key)

        version = ModelVersion(
            id=version_id,
            registered_model_id=model.id,
            version=next_version,
            experiment_id=experiment.id,
            dataset_version_id=experiment.dataset_version_id,
            algorithm=experiment.algorithm,
            framework=_framework_for(experiment.algorithm),
            stage=ModelStage.NONE,
            metrics=experiment.metrics,
            params=experiment.params,
            artifact_key=model_key,
            artifact_sha256=artifact_sha256,
            reference_profile=reference_profile,
            created_by=user_id,
        )
        db.add(version)
        model.latest_version = next_version
        model.updated_at = datetime.now(UTC)
        if description is not None and model.description != description:
            model.description = description
        db.add(model)
        record_audit(
            db,
            workspace_id=project.workspace_id,
            project_id=project.id,
            user_id=user_id,
            action="model.registered",
            resource_type="model_version",
            resource_id=version.id,
            details={
                "model_name": model.name,
                "version": next_version,
                "experiment_id": experiment.id,
            },
            ip_address=ip_address,
        )
        db.flush()
        if commit:
            db.commit()
    except IntegrityError as exc:
        if commit:
            db.rollback()
        for key in copied:
            with contextlib.suppress(Exception):
                storage.delete(key)
        raise ConflictError(
            "Another registration modified this model concurrently. Retry the request."
        ) from exc
    except Exception:
        if commit:
            db.rollback()
        for key in copied:
            with contextlib.suppress(Exception):
                storage.delete(key)
        raise
    return version


def register_model(
    db: Session,
    user: User,
    payload: ModelRegisterRequest,
    ip_address: str | None = None,
) -> ModelVersionSummary:
    require_project(db, user, payload.project_id, write=True)
    experiment = ExperimentRepository(db).get(payload.experiment_id)
    if experiment is None or experiment.project_id != payload.project_id:
        raise NotFoundError("Experiment not found.")
    version = register_experiment_as_model(
        db,
        experiment_id=experiment.id,
        user_id=user.id,
        model_name=payload.name,
        description=payload.description,
        add_to_existing=False,
        ip_address=ip_address,
    )
    return _version_summary(version, problem_type=experiment.problem_type)


def register_version(
    db: Session,
    user: User,
    model_id: str,
    experiment_id: str,
    description: str | None = None,
    ip_address: str | None = None,
) -> ModelVersionSummary:
    model = RegistryRepository(db).get_model(model_id)
    if model is None:
        raise NotFoundError("Registered model not found.")
    require_project(db, user, model.project_id, write=True)
    if description is not None and description != model.description:
        model.description = description
        db.add(model)
    version = register_experiment_as_model(
        db,
        experiment_id=experiment_id,
        user_id=user.id,
        model_name=model.name,
        model_id=model.id,
        ip_address=ip_address,
    )
    return _version_summary(version, problem_type=version.experiment.problem_type)


def list_models(
    db: Session, user: User, *, project_id: str, search: str | None, page: int, page_size: int
) -> tuple[list[ModelSummary], int]:
    require_project(db, user, project_id)
    repository = RegistryRepository(db)
    models, total = repository.list_models(project_id, search, (page - 1) * page_size, page_size)
    return [_model_summary(model) for model in models], total


def get_model(db: Session, user: User, model_id: str) -> ModelDetail:
    repository = RegistryRepository(db)
    model = repository.get_model_detail(model_id)
    if model is None:
        raise NotFoundError("Registered model not found.")
    require_project(db, user, model.project_id)
    versions = sorted(model.versions, key=lambda version: version.version, reverse=True)
    counts = repository.deployment_counts([version.id for version in versions])
    summary = _model_summary(model, versions)
    return ModelDetail(
        **summary.model_dump(),
        versions=[
            _version_summary(version, deployment_count=counts.get(version.id, 0))
            for version in versions
        ],
    )


def list_versions(db: Session, user: User, model_id: str) -> list[ModelVersionSummary]:
    repository = RegistryRepository(db)
    model = repository.get_model(model_id)
    if model is None:
        raise NotFoundError("Registered model not found.")
    require_project(db, user, model.project_id)
    versions = repository.list_versions(model.id)
    counts = repository.deployment_counts([version.id for version in versions])
    return [
        _version_summary(version, deployment_count=counts.get(version.id, 0))
        for version in versions
    ]


def get_version(db: Session, user: User, version_id: str) -> ModelVersionSummary:
    repository = RegistryRepository(db)
    version = repository.get_version(version_id)
    if version is None:
        raise NotFoundError("Model version not found.")
    require_project(db, user, version.registered_model.project_id)
    counts = repository.deployment_counts([version.id])
    return _version_summary(version, deployment_count=counts.get(version.id, 0))


def set_stage(
    db: Session,
    user: User,
    version_id: str,
    stage: str,
    ip_address: str | None = None,
) -> ModelVersionSummary:
    if stage not in {ModelStage.NONE, ModelStage.STAGING, ModelStage.PRODUCTION}:
        raise ValidationError("Invalid model stage.")
    repository = RegistryRepository(db)
    version = repository.get_version(version_id)
    if version is None:
        raise NotFoundError("Model version not found.")
    project, _role = require_project(db, user, version.registered_model.project_id, write=True)
    previous = version.stage
    if previous != stage:
        version.stage = stage
        version.updated_at = datetime.now(UTC)
        db.add(version)
        record_audit(
            db,
            workspace_id=project.workspace_id,
            project_id=project.id,
            user_id=user.id,
            action="model.promoted",
            resource_type="model_version",
            resource_id=version.id,
            details={
                "model_name": version.registered_model.name,
                "version": version.version,
                "from_stage": previous,
                "to_stage": stage,
            },
            ip_address=ip_address,
        )
        db.commit()
    counts = repository.deployment_counts([version.id])
    return _version_summary(version, deployment_count=counts.get(version.id, 0))


def archive_version(
    db: Session, user: User, version_id: str, ip_address: str | None = None
) -> ModelVersionSummary:
    repository = RegistryRepository(db)
    version = repository.get_version(version_id)
    if version is None:
        raise NotFoundError("Model version not found.")
    project, _role = require_project(db, user, version.registered_model.project_id, write=True)
    if version.stage != ModelStage.ARCHIVED:
        version.stage = ModelStage.ARCHIVED
        version.updated_at = datetime.now(UTC)
        db.add(version)
        record_audit(
            db,
            workspace_id=project.workspace_id,
            project_id=project.id,
            user_id=user.id,
            action="model.archived",
            resource_type="model_version",
            resource_id=version.id,
            details={
                "model_name": version.registered_model.name,
                "version": version.version,
            },
            ip_address=ip_address,
        )
        db.commit()
    counts = repository.deployment_counts([version.id])
    return _version_summary(version, deployment_count=counts.get(version.id, 0))


def prepare_download(
    db: Session, user: User, version_id: str, ip_address: str | None = None
) -> tuple[str, Iterator[bytes]]:
    repository = RegistryRepository(db)
    version = repository.get_version(version_id)
    if version is None:
        raise NotFoundError("Model version not found.")
    project, _role = require_project(db, user, version.registered_model.project_id, write=True)
    storage = get_storage()
    if not storage.exists(version.artifact_key):
        raise ConflictError("The model artifact is missing from object storage.")
    record_audit(
        db,
        workspace_id=project.workspace_id,
        project_id=project.id,
        user_id=user.id,
        action="model.downloaded",
        resource_type="model_version",
        resource_id=version.id,
        details={"model_name": version.registered_model.name, "version": version.version},
        ip_address=ip_address,
    )
    db.commit()
    safe_name = "".join(
        character if character.isalnum() or character in {"-", "_", "."} else "-"
        for character in version.registered_model.name
    )
    filename = f"{safe_name or 'model'}-v{version.version}.joblib"
    return filename, storage.iter_chunks(version.artifact_key)


def compare_versions(
    db: Session, user: User, model_id: str, payload: VersionCompareRequest
) -> VersionCompareResponse:
    repository = RegistryRepository(db)
    model = repository.get_model(model_id)
    if model is None:
        raise NotFoundError("Registered model not found.")
    require_project(db, user, model.project_id)
    versions = repository.versions_by_ids(payload.version_ids)
    if len(versions) != len(set(payload.version_ids)):
        raise NotFoundError("One or more model versions were not found.")
    if any(version.registered_model_id != model.id for version in versions):
        raise ValidationError("All versions must belong to the requested model.")
    by_id = {version.id: version for version in versions}
    ordered = [by_id[version_id] for version_id in payload.version_ids]
    problem_types = {version.experiment.problem_type for version in ordered if version.experiment}
    if len(problem_types) > 1:
        raise ValidationError("Versions with different problem types cannot be compared.")
    problem_type = next(iter(problem_types), ProblemType.CLASSIFICATION)
    expected = list(metric_directions(problem_type).keys())
    metric_keys = [
        metric
        for metric in expected
        if any(
            isinstance(version.metrics.get(metric), (int, float))
            and not isinstance(version.metrics.get(metric), bool)
            for version in ordered
        )
    ]
    directions = {key: METRIC_DIRECTIONS.get(key, "max") for key in metric_keys}
    best: dict[str, str] = {}
    for metric in metric_keys:
        candidates = [
            (version.id, float_or_none(version.metrics.get(metric))) for version in ordered
        ]
        candidates = [(version_id, value) for version_id, value in candidates if value is not None]
        if not candidates:
            continue
        winner = (
            max(candidates, key=lambda item: item[1])
            if directions[metric] == "max"
            else min(candidates, key=lambda item: item[1])
        )
        best[metric] = winner[0]
    counts = repository.deployment_counts([version.id for version in ordered])
    return VersionCompareResponse(
        metric_keys=metric_keys,
        directions=directions,
        best=best,
        versions=[
            _version_summary(version, deployment_count=counts.get(version.id, 0))
            for version in ordered
        ],
    )
