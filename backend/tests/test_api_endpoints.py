from __future__ import annotations

import io

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import Project, User


def test_auth_and_user_flow(client: TestClient):
    # Register new user
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@atlas.dev",
            "password": "secure-password-123",
            "full_name": "New User",
            "workspace_name": "New Workspace",
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert "access_token" in data
    token = data["access_token"]

    # Call /auth/me
    res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["email"] == "newuser@atlas.dev"

    # Login
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "newuser@atlas.dev", "password": "secure-password-123"},
    )
    assert res.status_code == 200
    assert "access_token" in res.json()

    # Wrong password
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "newuser@atlas.dev", "password": "wrong-password"},
    )
    assert res.status_code == 401


def test_workspaces_and_projects(client: TestClient, auth_headers: dict[str, str]):
    # List workspaces
    res = client.get("/api/v1/workspaces", headers=auth_headers)
    assert res.status_code == 200
    workspaces = res.json()
    assert len(workspaces) >= 1
    workspace_id = workspaces[0]["id"]

    # List projects in workspace
    res = client.get(f"/api/v1/workspaces/{workspace_id}/projects", headers=auth_headers)
    assert res.status_code == 200
    projects = res.json()
    assert len(projects) >= 1

    # Create project
    res = client.post(
        f"/api/v1/workspaces/{workspace_id}/projects",
        json={"name": "Fraud Detection", "description": "Detect fraudulent transactions"},
        headers=auth_headers,
    )
    assert res.status_code == 201
    assert res.json()["name"] == "Fraud Detection"


def test_datasets_upload_and_preview(
    client: TestClient,
    auth_headers: dict[str, str],
    seed_user: User,
    db_session: Session,
    sample_csv: bytes,
):
    project = db_session.query(Project).first()
    assert project is not None

    # Upload dataset
    files = {"file": ("churn.csv", io.BytesIO(sample_csv), "text/csv")}
    data = {
        "project_id": project.id,
        "name": "Customer Churn",
        "description": "Telco customer data",
    }
    res = client.post("/api/v1/datasets", data=data, files=files, headers=auth_headers)
    assert res.status_code == 201, res.text
    dataset_version = res.json()
    assert dataset_version["row_count"] == 10
    assert dataset_version["column_count"] == 5

    # List datasets
    res = client.get(f"/api/v1/datasets?project_id={project.id}", headers=auth_headers)
    assert res.status_code == 200
    datasets = res.json()["items"]
    assert len(datasets) >= 1
    dataset_id = datasets[0]["id"]

    # Get dataset detail
    res = client.get(f"/api/v1/datasets/{dataset_id}", headers=auth_headers)
    assert res.status_code == 200
    detail = res.json()
    assert detail["dataset"]["name"] == "Customer Churn"

    # Preview version
    version_id = dataset_version["id"]
    res = client.get(f"/api/v1/dataset-versions/{version_id}/preview", headers=auth_headers)
    assert res.status_code == 200
    preview = res.json()
    assert preview["returned"] == 10
    assert len(preview["columns"]) == 5


def test_full_mlops_training_deploy_predict_and_monitor(
    client: TestClient,
    auth_headers: dict[str, str],
    seed_user: User,
    db_session: Session,
    training_csv: bytes,
):
    project = db_session.query(Project).first()
    assert project is not None

    # 1. Upload dataset
    files = {"file": ("churn_train.csv", io.BytesIO(training_csv), "text/csv")}
    data = {"project_id": project.id, "name": "Churn Pipeline Dataset"}
    res = client.post("/api/v1/datasets", data=data, files=files, headers=auth_headers)
    assert res.status_code == 201
    dataset_version_id = res.json()["id"]

    # 2. Create training job with two algorithms (runs synchronously in sync mode)
    job_payload = {
        "project_id": project.id,
        "dataset_version_id": dataset_version_id,
        "name": "Churn Classifier Comparison",
        "problem_type": "classification",
        "target_column": "churn",
        "feature_columns": ["age", "tenure", "monthly_charges", "contract"],
        "algorithms": [
            {"algorithm": "logistic_regression", "hyperparameters": {}},
            {"algorithm": "random_forest_classifier", "hyperparameters": {"n_estimators": 20}},
        ],
        "test_size": 0.2,
        "random_seed": 42,
        "cv_folds": 0,
        "register_model_name": None,
    }
    res = client.post("/api/v1/training-jobs", json=job_payload, headers=auth_headers)
    assert res.status_code == 202, res.text
    job_data = res.json()
    job_id = job_data["id"]

    # Verify job completed and experiments created
    res = client.get(f"/api/v1/training-jobs/{job_id}", headers=auth_headers)
    assert res.status_code == 200
    job_detail = res.json()
    assert job_detail["status"] == "completed", (
        f"Job failed: error={job_detail.get('error_message')} logs={job_detail.get('logs')}"
    )
    assert len(job_detail["experiments"]) == 2

    experiment_id = job_detail["experiments"][0]["id"]

    # 3. Register model
    res = client.post(
        "/api/v1/models",
        json={
            "project_id": project.id,
            "experiment_id": experiment_id,
            "name": "churn-risk-model",
            "description": "Production candidate model",
        },
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    model_version = res.json()
    model_version_id = model_version["id"]
    registered_model_id = model_version["registered_model_id"]
    assert registered_model_id is not None
    assert model_version["version"] == 1

    # Promote model version to production
    res = client.post(
        f"/api/v1/model-versions/{model_version_id}/promote",
        json={"stage": "production"},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["stage"] == "production"

    # 4. Deploy model
    deploy_payload = {
        "project_id": project.id,
        "model_version_id": model_version_id,
        "name": "churn-realtime-api",
        "description": "Monitored prediction endpoint",
        "config": {
            "psi_threshold": 0.2,
            "drift_share_threshold": 0.3,
            "performance_degradation_threshold": 0.15,
            "min_samples": 5,
            "window_hours": 24,
            "auto_retrain_on_drift": False,
            "auto_retrain_cooldown_hours": 12,
        },
    }
    res = client.post("/api/v1/deployments", json=deploy_payload, headers=auth_headers)
    assert res.status_code == 201, res.text
    deployment = res.json()
    deployment_id = deployment["id"]
    api_key = deployment["api_key"]
    assert api_key is not None

    # Check health
    res = client.get(f"/api/v1/deployments/{deployment_id}/health", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["healthy"] is True

    # 5. Score predictions through API key
    predict_payload = {
        "records": [
            {"age": 28, "tenure": 10, "monthly_charges": 60.0, "contract": "month-to-month"},
            {"age": 55, "tenure": 48, "monthly_charges": 95.0, "contract": "two-year"},
            {"age": 33, "tenure": 15, "monthly_charges": 70.0, "contract": "one-year"},
            {"age": 42, "tenure": 24, "monthly_charges": 82.5, "contract": "month-to-month"},
            {"age": 60, "tenure": 50, "monthly_charges": 105.0, "contract": "two-year"},
        ]
    }
    res = client.post(
        f"/api/v1/predictions/{deployment_id}",
        json=predict_payload,
        headers={"X-API-Key": api_key},
    )
    assert res.status_code == 200, res.text
    pred_res = res.json()
    assert len(pred_res["predictions"]) == 5
    assert pred_res["latency_ms"] >= 0.0

    # 6. Verify prediction logs
    res = client.get(f"/api/v1/deployments/{deployment_id}/predictions", headers=auth_headers)
    assert res.status_code == 200
    logs = res.json()["items"]
    assert len(logs) == 5
    pred_log_id = logs[0]["id"]

    # 7. Submit ground-truth feedback
    res = client.post(
        "/api/v1/predictions/feedback",
        json={"items": [{"prediction_id": pred_log_id, "actual": 0}]},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["updated"] == 1

    # 8. Run monitoring scan
    res = client.post(f"/api/v1/deployments/{deployment_id}/monitoring/run", headers=auth_headers)
    assert res.status_code == 200, res.text
    monitor_res = res.json()
    assert monitor_res["deployment_id"] == deployment_id
    assert monitor_res["sample_count"] == 5

    # 9. Retrain deployment
    res = client.post(
        f"/api/v1/deployments/{deployment_id}/retrain",
        json={"name": "Automated Retrain Run"},
        headers=auth_headers,
    )
    assert res.status_code == 202, res.text
    retrain_job = res.json()
    assert retrain_job["status"] == "completed"
    assert retrain_job["retrain_source_deployment_id"] == deployment_id

    # Retrain comparison
    res = client.get(
        f"/api/v1/deployments/{deployment_id}/retrain/comparison", headers=auth_headers
    )
    assert res.status_code == 200
    comp = res.json()
    assert comp["deployment_id"] == deployment_id
    assert len(comp["candidates"]) >= 1
