from __future__ import annotations

import io
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import Project, User, Workspace


def test_workspace_invites_audit_and_alert_channels(
    client: TestClient,
    auth_headers: dict[str, str],
    seed_user: User,
    db_session: Session,
):
    workspace = db_session.query(Workspace).first()
    project = db_session.query(Project).first()
    assert workspace is not None and project is not None

    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/invites",
        json={"email": "new-member@atlas.dev", "role": "viewer"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    invite = response.json()
    assert invite["status"] == "pending"
    assert invite["token"]

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "new-member@atlas.dev",
            "password": "secure-password-123",
            "full_name": "New Member",
            "workspace_name": "Personal Workspace",
        },
    )
    assert response.status_code == 201, response.text
    member_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    response = client.get(f"/api/v1/invites/{invite['token']}", headers=member_headers)
    assert response.status_code == 200, response.text
    assert response.json()["email"] == "new-member@atlas.dev"

    response = client.post(f"/api/v1/invites/{invite['token']}/accept", headers=member_headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "accepted"

    members = client.get(f"/api/v1/workspaces/{workspace.id}/members", headers=auth_headers)
    assert members.status_code == 200, members.text
    new_member = next(item for item in members.json() if item["email"] == "new-member@atlas.dev")
    assert new_member["role"] == "viewer"

    response = client.patch(
        f"/api/v1/workspaces/{workspace.id}/members/{new_member['user_id']}",
        json={"role": "member"},
        headers=auth_headers,
    )
    assert response.status_code == 204, response.text

    audit = client.get(
        f"/api/v1/workspaces/{workspace.id}/audit-events?limit=100",
        headers=auth_headers,
    )
    assert audit.status_code == 200, audit.text
    actions = {event["action"] for event in audit.json()["items"]}
    assert {"member.invited", "member.joined", "member.role_updated"} <= actions

    response = client.post(
        f"/api/v1/projects/{project.id}/alert-channels",
        json={
            "name": "  Churn alerts  ",
            "kind": "webhook",
            "target_url": "https://alerts.example.invalid/hook",
            "secret": "test-webhook-secret",
            "min_status": "critical",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    channel = response.json()
    assert channel["name"] == "Churn alerts"
    assert channel["has_secret"] is True
    assert "secret" not in channel

    with patch("app.services.alerts._post_json", return_value=(204, None)) as post_json:
        response = client.post(
            f"/api/v1/projects/{project.id}/alert-channels/{channel['id']}/test",
            headers=auth_headers,
        )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True
    assert response.json()["response_code"] == 204
    assert post_json.call_args.args[0] == "https://alerts.example.invalid/hook"
    assert "X-Atlas-Signature" in post_json.call_args.args[2]

    response = client.patch(
        f"/api/v1/projects/{project.id}/alert-channels/{channel['id']}",
        json={"enabled": False, "name": "Churn alerts paused"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["enabled"] is False
    assert response.json()["name"] == "Churn alerts paused"

    response = client.delete(
        f"/api/v1/projects/{project.id}/alert-channels/{channel['id']}",
        headers=auth_headers,
    )
    assert response.status_code == 204, response.text
    channels = client.get(f"/api/v1/projects/{project.id}/alert-channels", headers=auth_headers)
    assert channels.status_code == 200, channels.text
    assert channels.json() == []


def test_batch_prediction_challenger_explanations_and_lineage(
    client: TestClient,
    auth_headers: dict[str, str],
    seed_user: User,
    db_session: Session,
    training_csv: bytes,
):
    project = db_session.query(Project).first()
    assert project is not None

    response = client.post(
        "/api/v1/datasets",
        data={"project_id": project.id, "name": "Feature test dataset"},
        files={"file": ("training.csv", io.BytesIO(training_csv), "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    dataset_version_id = response.json()["id"]

    response = client.post(
        "/api/v1/training-jobs",
        json={
            "project_id": project.id,
            "dataset_version_id": dataset_version_id,
            "name": "Feature test training",
            "problem_type": "classification",
            "target_column": "churn",
            "feature_columns": ["age", "tenure", "monthly_charges", "contract"],
            "algorithms": [
                {"algorithm": "logistic_regression", "hyperparameters": {}},
                {
                    "algorithm": "random_forest_classifier",
                    "hyperparameters": {"n_estimators": 20},
                },
            ],
            "test_size": 0.2,
            "random_seed": 42,
            "cv_folds": 0,
            "register_model_name": None,
        },
        headers=auth_headers,
    )
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["status"] == "completed"
    assert len(job["experiments"]) == 2
    experiment_ids = [item["id"] for item in job["experiments"]]

    response = client.post(
        "/api/v1/models",
        json={
            "project_id": project.id,
            "experiment_id": experiment_ids[0],
            "name": "Feature Test Model",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    champion = response.json()
    model_id = champion["registered_model_id"]

    response = client.post(
        f"/api/v1/models/{model_id}/versions",
        json={"experiment_id": experiment_ids[1]},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    challenger = response.json()
    assert challenger["registered_model_id"] == model_id
    assert challenger["version"] == 2

    response = client.post(
        "/api/v1/deployments",
        json={
            "project_id": project.id,
            "model_version_id": champion["id"],
            "name": "Feature test deployment",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    deployment = response.json()
    deployment_id = deployment["id"]

    batch_response = client.post(
        f"/api/v1/deployments/{deployment_id}/batch-predictions",
        files={"file": ("scoring.csv", io.BytesIO(training_csv), "text/csv")},
        headers=auth_headers,
    )
    assert batch_response.status_code == 201, batch_response.text
    batch = batch_response.json()
    assert batch["status"] == "completed"
    assert batch["success_count"] == batch["row_count"]
    assert batch["failed_count"] == 0
    assert "churn" not in batch["columns"]
    assert "prediction" in batch["columns"]

    response = client.get(
        f"/api/v1/deployments/{deployment_id}/batch-predictions/{batch['id']}/download",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "prediction" in response.text.splitlines()[0]

    response = client.post(
        f"/api/v1/deployments/{deployment_id}/explain",
        json={
            "record": {
                "age": 42,
                "tenure": 24,
                "monthly_charges": 82.5,
                "contract": "month-to-month",
            }
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    explanation = response.json()
    assert "permutation" in explanation["method"]
    assert explanation["model_version_id"] == champion["id"]
    assert explanation["contributions"]
    assert explanation["background_samples"] > 0

    response = client.put(
        f"/api/v1/deployments/{deployment_id}/challenger",
        json={"model_version_id": challenger["id"], "traffic_percent": 25},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["challenger_version_id"] == challenger["id"]
    assert response.json()["traffic_percent"] == 25

    response = client.patch(
        f"/api/v1/deployments/{deployment_id}/challenger",
        json={"traffic_percent": 40},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["traffic_percent"] == 40

    response = client.get(f"/api/v1/projects/{project.id}/lineage", headers=auth_headers)
    assert response.status_code == 200, response.text
    lineage = response.json()
    kinds = {node["kind"] for node in lineage["nodes"]}
    assert {"dataset", "training_job", "experiment", "model_version", "deployment"} <= kinds
    assert lineage["edges"]
