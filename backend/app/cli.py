from __future__ import annotations

import argparse
import io
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("atlas.cli")

DEMO_EMAIL = "demo@atlasmlops.dev"
DEMO_PASSWORD = "demo-password-123"  # noqa: S105 - documented demo credential
DEMO_WORKSPACE = "Demo Workspace"
DEMO_PROJECT = "Customer Churn"
DEMO_DATASET = "Telco customer churn"
DEMO_JOB = "Churn baseline"
DEMO_MODEL = "Churn Propensity"
DEMO_DEPLOYMENT = "Churn prediction API"


def _bootstrap() -> None:
    import app.models  # noqa: F401 - registers all mapped tables
    from app.core.config import get_settings
    from app.core.logging import configure_logging
    from app.db.base import Base
    from app.db.session import SessionLocal, engine

    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    Base.metadata.create_all(bind=engine)
    return SessionLocal, settings


def _ensure_user(db, email: str, password: str):
    from sqlalchemy import select

    from app.models.user import User
    from app.schemas.auth import RegisterRequest
    from app.services import users as user_service

    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is not None:
        return user
    user_service.register_user(
        db,
        RegisterRequest(
            email=email,
            password=password,
            full_name="Demo User",
            workspace_name=DEMO_WORKSPACE,
        ),
        "127.0.0.1",
    )
    return db.scalar(select(User).where(User.email == email.lower()))


def _ensure_workspace(db, user):
    from app.models.user import Workspace, WorkspaceMember
    from app.services import users as user_service

    workspaces = user_service.list_workspaces(db, user)
    for workspace in workspaces:
        if workspace.name == DEMO_WORKSPACE:
            return workspace
    if workspaces:
        return workspaces[0]
    workspace = Workspace(name=DEMO_WORKSPACE, slug="demo-workspace")
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
    db.commit()
    return user_service.list_workspaces(db, user)[0]


def _ensure_project(db, user, workspace):
    from app.schemas.workspace import ProjectCreateRequest
    from app.services import users as user_service

    for project in user_service.list_projects(db, user, workspace.id):
        if project.name == DEMO_PROJECT:
            return project
    return user_service.create_project(
        db,
        user,
        workspace.id,
        ProjectCreateRequest(
            name=DEMO_PROJECT,
            description="Demo project for customer churn prediction.",
        ),
        "127.0.0.1",
    )


def _ensure_dataset(db, user, project, data_file: Path):
    from app.services import datasets as dataset_service

    items, _ = dataset_service.list_datasets(
        db, user, project_id=project.id, search=DEMO_DATASET, page=1, page_size=100
    )
    for item in items:
        if item.name == DEMO_DATASET:
            detail = dataset_service.get_dataset(db, user, item.id)
            return detail.latest_version, detail.dataset
    payload = data_file.read_bytes()
    version = dataset_service.create_dataset(
        db,
        user,
        project_id=project.id,
        name=DEMO_DATASET,
        description="Synthetic telco churn dataset with calibrated signal.",
        stream=io.BytesIO(payload),
        filename=data_file.name,
        content_type="text/csv",
        ip_address="127.0.0.1",
    )
    return version, dataset_service.get_dataset(db, user, version.dataset_id).dataset


def _ensure_training_job(db, user, project, version_id: str):
    from app.schemas.training import (
        AlgorithmSelection,
        TrainingJobCreateRequest,
    )
    from app.services import training as training_service

    items, _ = training_service.list_training_jobs(
        db,
        user,
        project_id=project.id,
        status=None,
        search=None,
        page=1,
        page_size=100,
    )
    for item in items:
        if item.name == DEMO_JOB:
            return training_service.get_training_job(db, user, item.id)
    return training_service.create_training_job(
        db,
        user,
        TrainingJobCreateRequest(
            project_id=project.id,
            dataset_version_id=version_id,
            name=DEMO_JOB,
            problem_type="classification",
            target_column="churn",
            feature_columns=[
                "tenure_months",
                "monthly_charges",
                "total_charges",
                "contract_type",
                "payment_method",
                "internet_service",
                "support_tickets",
                "autopay",
            ],
            algorithms=[
                AlgorithmSelection(
                    algorithm="logistic_regression",
                    hyperparameters={"C": 1.0, "max_iter": 500},
                ),
                AlgorithmSelection(
                    algorithm="random_forest_classifier",
                    hyperparameters={
                        "n_estimators": 200,
                        "max_depth": 8,
                        "min_samples_split": 4,
                    },
                ),
                AlgorithmSelection(
                    algorithm="gradient_boosting_classifier",
                    hyperparameters={
                        "n_estimators": 150,
                        "learning_rate": 0.08,
                        "max_depth": 3,
                    },
                ),
            ],
            test_size=0.2,
            random_seed=42,
            cv_folds=3,
            register_model_name=DEMO_MODEL,
        ),
        "127.0.0.1",
    )


def _ensure_deployment(db, user, project):
    from app.schemas.deployment import DeploymentCreateRequest
    from app.services import deployments as deployment_service
    from app.services import registry as registry_service

    items, _ = deployment_service.list_deployments(
        db,
        user,
        project_id=project.id,
        status=None,
        page=1,
        page_size=100,
    )
    for item in items:
        if item.name == DEMO_DEPLOYMENT:
            return item, None
    models, _ = registry_service.list_models(
        db, user, project_id=project.id, search=DEMO_MODEL, page=1, page_size=100
    )
    model = next((item for item in models if item.name == DEMO_MODEL), None)
    if model is None:
        return None, None
    versions = registry_service.list_versions(db, user, model.id)
    if not versions:
        return None, None
    created = deployment_service.create_deployment(
        db,
        user,
        DeploymentCreateRequest(
            project_id=project.id,
            model_version_id=versions[0].id,
            name=DEMO_DEPLOYMENT,
            description="Demo deployment for the churn model.",
        ),
        "127.0.0.1",
    )
    return created, created.api_key


def seed_demo(args: argparse.Namespace) -> int:
    from app.core.config import get_settings

    os.environ.setdefault("JOB_EXECUTION_MODE", "sync")
    if get_settings().environment == "production":
        print("Demo seeding is available only in development and test.", file=sys.stderr)
        return 2
    SessionLocal, settings = _bootstrap()
    data_file = Path(args.data_file).expanduser().resolve()
    if not data_file.exists():
        print(f"Demo dataset not found: {data_file}", file=sys.stderr)
        return 2
    with SessionLocal() as db:
        user = _ensure_user(db, args.email, args.password)
        workspace = _ensure_workspace(db, user)
        project = _ensure_project(db, user, workspace)
        version, dataset = _ensure_dataset(db, user, project, data_file)
        if version is None:
            print("No dataset version is available.", file=sys.stderr)
            return 1
        job = _ensure_training_job(db, user, project, version.id)
        deployment, api_key = _ensure_deployment(db, user, project)

    print("Atlas demo data is ready.")
    print(f"  Login:    {args.email}")
    print(f"  Project:  {project.name} ({project.id})")
    print(f"  Dataset:  {dataset.name}, version {version.version}")
    print(f"  Job:      {job.name} [{job.status}] ({job.id})")
    if deployment is not None:
        print(f"  Deploy:   {deployment.name} [{deployment.status}] ({deployment.id})")
    if api_key:
        print(f"  API key:  {api_key} (store it now; it is not shown again)")
    print(f"  MLflow:   {settings.mlflow_tracking_uri}")
    return 0


def init_db(args: argparse.Namespace) -> int:
    _, settings = _bootstrap()
    print(f"Database schema ensured at {settings.database_url}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="atlas", description="Atlas MLOps CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    seed = subparsers.add_parser("seed-demo", help="Create demo user, data, model, deployment")
    seed.add_argument("--email", default=DEMO_EMAIL)
    seed.add_argument("--password", default=DEMO_PASSWORD)
    seed.add_argument(
        "--data-file",
        default=str(Path(__file__).resolve().parents[2] / "demo-data" / "customer_churn.csv"),
    )
    seed.set_defaults(handler=seed_demo)
    init = subparsers.add_parser("init-db", help="Create database tables (development)")
    init.set_defaults(handler=init_db)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
