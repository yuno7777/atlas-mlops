from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.ml.evaluation import primary_metric
from app.models.registry import ModelVersion
from app.models.user import User
from app.schemas.modelops import ModelCardResponse
from app.services.access import require_project


def get_model_card(db: Session, user: User, version_id: str) -> ModelCardResponse:
    version = db.get(ModelVersion, version_id)
    if version is None:
        raise NotFoundError("Model version not found.")
    require_project(db, user, version.registered_model.project_id)
    experiment = version.experiment
    dataset_version = version.dataset_version
    dataset = dataset_version.dataset if dataset_version else None
    job = experiment.job if experiment else None
    metrics = dict(experiment.metrics or {}) if experiment else dict(version.metrics or {})
    fairness = metrics.pop("fairness", None)
    metric_values = {
        key: value
        for key, value in metrics.items()
        if isinstance(value, (int, float, str, bool)) or value is None
    }
    split_size = float((experiment.params or {}).get("test_size", 0.2)) if experiment else 0.2
    cv_folds = int((experiment.params or {}).get("cv_folds", 0)) if experiment else 0
    sensitive_columns = (experiment.params or {}).get("sensitive_columns", []) if experiment else []
    return ModelCardResponse(
        schema_version="1.0",
        model={
            "name": version.registered_model.name,
            "version": version.version,
            "algorithm": version.algorithm,
            "framework": version.framework,
            "problem_type": experiment.problem_type if experiment else None,
            "stage": version.stage,
        },
        intended_use={
            "primary_metric": primary_metric(experiment.problem_type) if experiment else None,
            "intended_use": version.registered_model.description
            or "General purpose evaluation; document the deployment context before production use.",
            "out_of_scope": "High impact decisions without domain review, consent, and human oversight.",
        },
        training_data={
            "dataset": dataset.name if dataset else None,
            "dataset_version": dataset_version.version if dataset_version else None,
            "rows": dataset_version.row_count if dataset_version else None,
            "checksum": dataset_version.checksum if dataset_version else None,
            "feature_count": len(
                (version.reference_profile or {}).get("schema", {}).get("features", [])
            ),
            "audit_columns_excluded_from_features": sensitive_columns,
        },
        evaluation={
            "holdout_fraction": split_size,
            "cross_validation_folds": cv_folds,
            "metrics": metric_values,
            "primary_metric": primary_metric(experiment.problem_type) if experiment else None,
            "test_samples": metric_values.get("test_samples"),
        },
        fairness=fairness,
        limitations=[
            "Results describe the recorded dataset and split; they do not establish performance on future or out-of-domain data.",
            "Fairness summaries are descriptive group metrics and do not prove that a model is fair.",
            "Group estimates can be unstable when a subgroup has few evaluation samples.",
            "Review target definition, label quality, data permissions, and domain-specific risks before deployment.",
        ],
        monitoring={
            "reference_profile_version": (version.reference_profile or {}).get("version"),
            "recommended_checks": [
                "feature drift",
                "prediction drift",
                "labeled performance",
                "latency and failure rate",
            ],
        },
        provenance={
            "model_version_id": version.id,
            "experiment_id": version.experiment_id,
            "training_job_id": job.id if job else None,
            "artifact_sha256": version.artifact_sha256,
            "created_at": version.created_at,
            "generated_at": datetime.now(UTC),
        },
    )


def model_card_markdown(card: ModelCardResponse) -> str:
    data: dict[str, Any] = card.model_dump(mode="json")
    model = data["model"]
    training = data["training_data"]
    evaluation = data["evaluation"]
    lines = [
        f"# Model card: {model['name']} v{model['version']}",
        "",
        f"- Algorithm: `{model['algorithm']}` ({model['framework']})",
        f"- Problem type: {model['problem_type'] or 'unspecified'}",
        f"- Stage: {model['stage']}",
        "",
        "## Intended use",
        "",
        str(data["intended_use"]["intended_use"]),
        "",
        f"Out of scope: {data['intended_use']['out_of_scope']}",
        "",
        "## Training data",
        "",
        f"- Dataset: {training['dataset'] or 'unknown'} v{training['dataset_version'] or '—'}",
        f"- Rows: {training['rows'] or 'unknown'}",
        f"- Feature count: {training['feature_count']}",
        f"- Audit columns excluded from features: {', '.join(training['audit_columns_excluded_from_features']) or 'none'}",
        "",
        "## Evaluation",
        "",
        f"- Holdout fraction: {evaluation['holdout_fraction']}",
        f"- Cross-validation folds: {evaluation['cross_validation_folds']}",
        f"- Primary metric: {evaluation['primary_metric']}",
        "",
        "```json",
        json.dumps(evaluation["metrics"], indent=2, sort_keys=True),
        "```",
        "",
        "## Fairness assessment",
        "",
        "```json",
        json.dumps(data["fairness"] or {"status": "not_run"}, indent=2, sort_keys=True),
        "```",
        "",
        "## Limitations",
        "",
        *[f"- {item}" for item in data["limitations"]],
        "",
        "## Monitoring recommendations",
        "",
        *[f"- {item}" for item in data["monitoring"]["recommended_checks"]],
        "",
        "## Provenance",
        "",
        f"- Experiment: `{data['provenance']['experiment_id']}`",
        f"- Training job: `{data['provenance']['training_job_id']}`",
        f"- Artifact SHA-256: `{data['provenance']['artifact_sha256']}`",
        "",
    ]
    return "\n".join(lines)
