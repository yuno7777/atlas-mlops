"""Exercise the running Compose stack through the frontend proxy."""

from __future__ import annotations

import json
import secrets
import time
from http.client import HTTPConnection
from itertools import islice
from pathlib import Path
from typing import Any

API = "/api/v1"


def request(
    path: str,
    *,
    data: dict[str, Any] | bytes | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any] | list[Any]:
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    if isinstance(data, dict):
        data = json.dumps(data).encode()
    connection = HTTPConnection("127.0.0.1", 3000, timeout=15)
    try:
        connection.request("POST" if data is not None else "GET", path, data, request_headers)
        with connection.getresponse() as response:
            if response.status >= 400:
                raise RuntimeError(
                    f"{path} returned HTTP {response.status}: {response.read(1000).decode()}"
                )
            return json.load(response)
    finally:
        connection.close()


def main() -> None:
    readiness = request("/ready")
    assert readiness["status"] == "ready", readiness
    assert any(item["name"] == "redis" for item in readiness["checks"]), readiness

    suffix = secrets.token_hex(6)
    account = request(
        f"{API}/auth/register",
        data={
            "email": f"compose-{suffix}@example.com",
            "password": secrets.token_urlsafe(24),
            "full_name": "Compose Smoke",
            "workspace_name": f"Compose Smoke {suffix}",
        },
    )
    headers = {"Authorization": f"Bearer {account['access_token']}"}
    workspace = request(f"{API}/workspaces", headers=headers)[0]
    project = request(
        f"{API}/workspaces/{workspace['id']}/projects",
        data={"name": "Synthetic churn"},
        headers=headers,
    )
    csv_path = Path(__file__).resolve().parents[1] / "demo-data" / "customer_churn.csv"
    with csv_path.open("rb") as csv_file:
        sample = b"".join(islice(csv_file, 97))
    boundary = f"atlas-{suffix}"
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
        for key, value in {"project_id": project["id"], "name": "Synthetic churn"}.items()
    ]
    parts.extend(
        [
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="churn.csv"\r\n'
            "Content-Type: text/csv\r\n\r\n".encode(),
            sample,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    dataset = request(
        f"{API}/datasets",
        data=b"".join(parts),
        headers={**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    job = request(
        f"{API}/training-jobs",
        data={
            "project_id": project["id"],
            "dataset_version_id": dataset["id"],
            "problem_type": "classification",
            "target_column": "churn",
            "feature_columns": ["tenure_months", "monthly_charges"],
            "algorithms": [{"algorithm": "logistic_regression"}],
        },
        headers={**headers, "Idempotency-Key": suffix},
    )
    deadline = time.monotonic() + 120
    while job["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(1)
        job = request(f"{API}/training-jobs/{job['id']}", headers=headers)
    assert job["status"] == "completed", job
    experiment = job["experiments"][0]
    assert experiment["mlflow_run_id"] and not experiment["tracking_warning"], experiment

    version = request(
        f"{API}/models",
        data={"project_id": project["id"], "experiment_id": experiment["id"], "name": "Churn"},
        headers=headers,
    )
    deployment = request(
        f"{API}/deployments",
        data={"project_id": project["id"], "model_version_id": version["id"], "name": "Churn"},
        headers=headers,
    )
    result = request(
        f"{API}/predictions/{deployment['id']}",
        data={"records": [{"tenure_months": 5, "monthly_charges": 70.0}]},
        headers={"X-API-Key": deployment["api_key"], "X-Request-ID": f"compose-{suffix}"},
    )
    assert result["request_id"] == f"compose-{suffix}" and len(result["predictions"]) == 1, result
    print("Compose pipeline passed: upload, Celery training, MLflow, registry, and prediction.")


if __name__ == "__main__":
    main()
