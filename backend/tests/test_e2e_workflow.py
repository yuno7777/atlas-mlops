from __future__ import annotations

import io

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.dataset import DatasetVersion
from app.services.storage import get_storage
from app.services.training_runner import execute_training_job


def test_complete_mlops_lifecycle_e2e(client: TestClient, training_csv: bytes, db_session: Session):
    """Execute the full end-to-end definition-of-done workflow through HTTP endpoints."""
    # 1. Register user
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": "lead.mlops@atlas.dev",
            "password": "SecurePassword987!",
            "full_name": "Atlas Lead Engineer",
            "workspace_name": "Production MLOps",
        },
    )
    assert res.status_code == 201, res.text
    auth_data = res.json()
    token = auth_data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Get workspace & create project
    res = client.get("/api/v1/workspaces", headers=headers)
    assert res.status_code == 200
    workspaces = res.json()
    assert len(workspaces) >= 1
    workspace_id = workspaces[0]["id"]

    res = client.post(
        f"/api/v1/workspaces/{workspace_id}/projects",
        json={"name": "Customer Retention", "description": "Predict and prevent churn"},
        headers=headers,
    )
    assert res.status_code == 201
    project = res.json()
    project_id = project["id"]

    # 3. Upload dataset
    files = {"file": ("retention_data.csv", io.BytesIO(training_csv), "text/csv")}
    data = {"project_id": project_id, "name": "Customer Activity Records"}
    res = client.post("/api/v1/datasets", data=data, files=files, headers=headers)
    assert res.status_code == 201, res.text
    version = res.json()
    version_id = version["id"]
    assert version["row_count"] == 30
    assert version["column_count"] == 5

    # 4. Confirm ready + preview
    res = client.get(f"/api/v1/dataset-versions/{version_id}/preview", headers=headers)
    assert res.status_code == 200
    preview = res.json()
    assert preview["returned"] == 30
    assert len(preview["columns"]) == 5

    # 5. Create training job with two classification algorithms
    job_payload = {
        "project_id": project_id,
        "dataset_version_id": version_id,
        "name": "Retention Model Evaluation",
        "problem_type": "classification",
        "target_column": "churn",
        "feature_columns": ["age", "tenure", "monthly_charges", "contract"],
        "algorithms": [
            {"algorithm": "logistic_regression", "hyperparameters": {}},
            {"algorithm": "random_forest_classifier", "hyperparameters": {"n_estimators": 25}},
        ],
        "test_size": 0.2,
        "random_seed": 42,
        "cv_folds": 0,
        "register_model_name": None,
    }
    job_headers = {**headers, "Idempotency-Key": "retention-smoke", "X-Request-ID": "train-smoke"}
    res = client.post("/api/v1/training-jobs", json=job_payload, headers=job_headers)
    assert res.status_code == 202, res.text
    job_id = res.json()["id"]

    replay = client.post("/api/v1/training-jobs", json=job_payload, headers=job_headers)
    assert replay.status_code == 202
    assert replay.json()["id"] == job_id
    conflict = client.post(
        "/api/v1/training-jobs", json={**job_payload, "random_seed": 99}, headers=job_headers
    )
    assert conflict.status_code == 409
    execute_training_job(job_id)  # Redelivery after completion does not duplicate experiments.

    # 6. Verify both experiments completed with real metrics
    res = client.get(f"/api/v1/training-jobs/{job_id}", headers=headers)
    assert res.status_code == 200
    job_detail = res.json()
    assert job_detail["status"] == "completed"
    experiments = job_detail["experiments"]
    assert len(experiments) == 2
    assert job_detail["config"]["request_id"] == "train-smoke"

    exp1, exp2 = experiments[0], experiments[1]
    assert exp1["status"] == "completed"
    assert exp2["status"] == "completed"
    assert "accuracy" in exp1["metrics"]
    assert "accuracy" in exp2["metrics"]

    # 7. Compare experiments via API
    res = client.post(
        "/api/v1/experiments/compare",
        json={"experiment_ids": [exp1["id"], exp2["id"]]},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    comparison = res.json()
    assert len(comparison["experiments"]) == 2
    assert comparison["problem_type"] == "classification"
    assert "accuracy" in comparison["metric_keys"]

    # Pick the best experiment
    best_exp_id = (
        exp1["id"]
        if exp1["metrics"].get("accuracy", 0) >= exp2["metrics"].get("accuracy", 0)
        else exp2["id"]
    )

    # 8. Register and promote model
    res = client.post(
        "/api/v1/models",
        json={
            "project_id": project_id,
            "experiment_id": best_exp_id,
            "name": "churn-champion",
            "description": "Evaluated champion classifier",
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    model_version = res.json()
    model_version_id = model_version["id"]
    assert model_version["version"] == 1
    detail = client.get(f"/api/v1/experiments/{best_exp_id}", headers=headers)
    assert detail.status_code == 200
    provenance = detail.json()["reference_profile"]["provenance"]
    assert provenance["dataset_sha256"] == version["checksum"]
    assert provenance["model_sha256"] == model_version["artifact_sha256"]
    assert "scikit-learn" in provenance["packages"]

    res = client.post(
        f"/api/v1/model-versions/{model_version_id}/promote",
        json={"stage": "production"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["stage"] == "production"

    # 9. Deploy model
    deploy_payload = {
        "project_id": project_id,
        "model_version_id": model_version_id,
        "name": "churn-live-v1",
        "description": "Live production endpoint",
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
    res = client.post("/api/v1/deployments", json=deploy_payload, headers=headers)
    assert res.status_code == 201, res.text
    deployment = res.json()
    deployment_id = deployment["id"]
    api_key = deployment["api_key"]
    assert api_key.startswith("atlas_")

    # 10. Predict normal records & submit feedback
    normal_records = [
        {"age": 28, "tenure": 10, "monthly_charges": 60.0, "contract": "month-to-month"},
        {"age": 55, "tenure": 48, "monthly_charges": 95.0, "contract": "two-year"},
        {"age": 35, "tenure": 20, "monthly_charges": 75.0, "contract": "one-year"},
        {"age": 42, "tenure": 15, "monthly_charges": 65.0, "contract": "month-to-month"},
        {"age": 60, "tenure": 60, "monthly_charges": 110.0, "contract": "two-year"},
    ]
    res = client.post(
        f"/api/v1/predictions/{deployment_id}",
        json={"records": normal_records},
        headers={"X-API-Key": api_key, "X-Request-ID": "predict-smoke"},
    )
    assert res.status_code == 200, res.text
    assert res.headers["X-Request-ID"] == res.json()["request_id"] == "predict-smoke"
    preds = res.json()["predictions"]
    assert len(preds) == 5
    for invalid in ({"records": [{"age": ["nested"]}]}, {"records": normal_records, "extra": True}):
        rejected = client.post(
            f"/api/v1/predictions/{deployment_id}", json=invalid, headers={"X-API-Key": api_key}
        )
        assert rejected.status_code == 422

    res = client.get(f"/api/v1/deployments/{deployment_id}/predictions", headers=headers)
    assert res.status_code == 200
    logs = res.json()["items"]
    assert len(logs) == 5

    # Feedback
    res = client.post(
        "/api/v1/predictions/feedback",
        json={"items": [{"prediction_id": logs[0]["id"], "actual": 0}]},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["updated"] == 1

    # 11. Run monitoring scan
    res = client.post(f"/api/v1/deployments/{deployment_id}/monitoring/run", headers=headers)
    assert res.status_code == 200, res.text
    monitoring = res.json()
    assert monitoring["sample_count"] == 5
    assert "data_drift_detected" in monitoring

    # 12. Trigger retraining
    res = client.post(
        f"/api/v1/deployments/{deployment_id}/retrain",
        json={"name": "Candidate Challenger Retrain"},
        headers=headers,
    )
    assert res.status_code == 202, res.text
    retrain_job = res.json()
    assert retrain_job["status"] == "completed"
    assert retrain_job["retrain_source_deployment_id"] == deployment_id

    # Verify project dashboard overview reflects real entities
    res = client.get(f"/api/v1/projects/{project_id}/overview", headers=headers)
    assert res.status_code == 200, res.text
    overview = res.json()
    assert overview["counts"]["datasets"] >= 1
    assert overview["counts"]["experiments"] >= 2
    assert overview["counts"]["registered_models"] >= 1
    assert overview["counts"]["active_deployments"] >= 1
    assert overview["counts"]["predictions_7d"] >= 5

    # A modified object cannot silently change a pinned training input.
    dataset = db_session.get(DatasetVersion, version_id)
    assert dataset is not None
    get_storage().put_bytes(dataset.storage_key, training_csv + b"\n")
    tampered = client.post("/api/v1/training-jobs", json=job_payload, headers=headers)
    assert tampered.status_code == 202
    assert tampered.json()["status"] == "failed"
    assert "integrity check" in tampered.json()["error_message"]
    assert not tampered.json()["experiments"]
