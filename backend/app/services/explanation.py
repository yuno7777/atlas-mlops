from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.ml.explain import explain_record
from app.models.user import User
from app.repositories.deployments import DeploymentRepository
from app.schemas.explanation import ExplanationResponse, FeatureContribution
from app.services.access import require_project
from app.services.predictions import get_model_cache


def explain_deployment_prediction(
    db: Session,
    user: User,
    deployment_id: str,
    record: dict,
) -> ExplanationResponse:
    deployment = DeploymentRepository(db).get(deployment_id)
    if deployment is None:
        raise NotFoundError("Deployment not found.")
    require_project(db, user, deployment.project_id)
    version = deployment.model_version
    loaded = get_model_cache().get_or_load(version)
    if not loaded.reference_profile.get("schema", {}).get("features"):
        raise ValidationError("The deployed model has no feature schema.", status_code=503)
    outcome = explain_record(
        loaded.pipeline,
        loaded.reference_profile,
        loaded.problem_type,
        record,
    )
    return ExplanationResponse(
        deployment_id=deployment.id,
        model_version_id=version.id,
        model_version=version.version,
        problem_type=outcome["problem_type"],
        method=outcome["method"],
        baseline=outcome["baseline"],
        prediction=outcome["prediction"],
        contributions=[
            FeatureContribution(**contribution) for contribution in outcome["contributions"]
        ],
        background_samples=outcome["background_samples"],
        permutations=outcome["permutations"],
        latency_ms=outcome["latency_ms"],
    )
