from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dataset import Dataset, DatasetVersion
from app.models.deployment import Deployment
from app.models.registry import ModelVersion, RegisteredModel
from app.models.training import Experiment, TrainingJob
from app.models.user import User
from app.schemas.lineage import LineageEdge, LineageNode, LineageResponse
from app.services.access import require_project


def _node_id(kind: str, identifier: str) -> str:
    return f"{kind}:{identifier}"


def project_lineage(db: Session, user: User, project_id: str) -> LineageResponse:
    project, _role = require_project(db, user, project_id)
    nodes: list[LineageNode] = []
    edges: list[LineageEdge] = []

    datasets = list(
        db.execute(select(Dataset).where(Dataset.project_id == project.id)).scalars().all()
    )
    dataset_names = {dataset.id: dataset.name for dataset in datasets}
    versions = list(
        db.execute(
            select(DatasetVersion)
            .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
            .where(Dataset.project_id == project.id)
            .order_by(DatasetVersion.created_at.asc())
        )
        .scalars()
        .all()
    )
    for version in versions:
        nodes.append(
            LineageNode(
                id=_node_id("dataset", version.id),
                kind="dataset",
                label=dataset_names.get(version.dataset_id, "Dataset"),
                subtitle=f"v{version.version} · {version.row_count:,} rows",
                status=version.status,
                href=f"/datasets/{version.dataset_id}",
                details={
                    "dataset_version_id": version.id,
                    "version": version.version,
                    "row_count": version.row_count,
                    "column_count": version.column_count,
                    "checksum": version.checksum,
                    "created_at": version.created_at.isoformat(),
                },
            )
        )

    jobs = list(
        db.execute(
            select(TrainingJob)
            .where(TrainingJob.project_id == project.id)
            .order_by(TrainingJob.created_at.asc())
        )
        .scalars()
        .all()
    )
    for job in jobs:
        nodes.append(
            LineageNode(
                id=_node_id("job", job.id),
                kind="training_job",
                label=job.name,
                subtitle=f"{job.problem_type} · {job.status}",
                status=job.status,
                href=f"/training/{job.id}",
                details={
                    "training_job_id": job.id,
                    "problem_type": job.problem_type,
                    "target_column": job.target_column,
                    "algorithm_count": len(job.algorithms or []),
                    "created_at": job.created_at.isoformat(),
                },
            )
        )
        edges.append(
            LineageEdge(
                source=_node_id("dataset", job.dataset_version_id),
                target=_node_id("job", job.id),
                label="trains on",
            )
        )

    experiments = list(
        db.execute(
            select(Experiment)
            .where(Experiment.project_id == project.id)
            .order_by(Experiment.created_at.asc())
        )
        .scalars()
        .all()
    )
    for experiment in experiments:
        nodes.append(
            LineageNode(
                id=_node_id("experiment", experiment.id),
                kind="experiment",
                label=experiment.algorithm_label or experiment.algorithm,
                subtitle=experiment.status,
                status=experiment.status,
                href=f"/experiments/{experiment.id}",
                details={
                    "experiment_id": experiment.id,
                    "algorithm": experiment.algorithm,
                    "metrics": experiment.metrics,
                    "training_job_id": experiment.training_job_id,
                    "created_at": experiment.created_at.isoformat(),
                },
            )
        )
        edges.append(
            LineageEdge(
                source=_node_id("job", experiment.training_job_id),
                target=_node_id("experiment", experiment.id),
                label="produces",
            )
        )

    models = list(
        db.execute(
            select(RegisteredModel)
            .where(RegisteredModel.project_id == project.id)
            .order_by(RegisteredModel.created_at.asc())
        )
        .scalars()
        .all()
    )
    model_names = {model.id: model.name for model in models}
    model_versions = list(
        db.execute(
            select(ModelVersion)
            .join(RegisteredModel, RegisteredModel.id == ModelVersion.registered_model_id)
            .where(RegisteredModel.project_id == project.id)
            .order_by(ModelVersion.created_at.asc())
        )
        .scalars()
        .all()
    )
    for version in model_versions:
        nodes.append(
            LineageNode(
                id=_node_id("model", version.id),
                kind="model_version",
                label=f"{model_names.get(version.registered_model_id, 'Model')} v{version.version}",
                subtitle=f"{version.algorithm} · {version.stage}",
                status=version.stage,
                href=f"/models/{version.registered_model_id}",
                details={
                    "model_version_id": version.id,
                    "version": version.version,
                    "stage": version.stage,
                    "algorithm": version.algorithm,
                    "metrics": version.metrics,
                    "created_at": version.created_at.isoformat(),
                },
            )
        )
        edges.append(
            LineageEdge(
                source=_node_id("experiment", version.experiment_id),
                target=_node_id("model", version.id),
                label="registers",
            )
        )

    deployments = list(
        db.execute(
            select(Deployment)
            .where(Deployment.project_id == project.id)
            .order_by(Deployment.created_at.asc())
        )
        .scalars()
        .all()
    )
    for deployment in deployments:
        nodes.append(
            LineageNode(
                id=_node_id("deployment", deployment.id),
                kind="deployment",
                label=deployment.name,
                subtitle=(
                    f"{deployment.status}"
                    + (
                        f" · challenger {deployment.challenger_traffic_percent}%"
                        if deployment.challenger_model_version_id
                        else ""
                    )
                ),
                status=deployment.status,
                href=f"/deployments/{deployment.id}",
                details={
                    "deployment_id": deployment.id,
                    "status": deployment.status,
                    "model_version_id": deployment.model_version_id,
                    "challenger_model_version_id": deployment.challenger_model_version_id,
                    "challenger_traffic_percent": deployment.challenger_traffic_percent,
                    "created_at": deployment.created_at.isoformat(),
                },
            )
        )
        edges.append(
            LineageEdge(
                source=_node_id("model", deployment.model_version_id),
                target=_node_id("deployment", deployment.id),
                label="serves",
            )
        )
        if deployment.challenger_model_version_id:
            edges.append(
                LineageEdge(
                    source=_node_id("model", deployment.challenger_model_version_id),
                    target=_node_id("deployment", deployment.id),
                    label="challenger",
                )
            )

    return LineageResponse(project_id=project.id, nodes=nodes, edges=edges)
