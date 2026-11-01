"""Upload synthetic data to Atlas, train baselines, and save experiment metrics."""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from generate_mock_datasets import DATASETS, generate

DATA_DIR = Path(__file__).resolve().parent / "mock-benchmarks"
PROJECT_NAME = "Synthetic Model Benchmarks"
DESCRIPTIONS = {
    "SaaS Customer Churn": "Synthetic subscription and product-usage data; target is churned (yes/no).",
    "Loan Repayment Risk": "Synthetic affordability and repayment history data; target is defaulted (yes/no).",
    "E-commerce Conversion": "Synthetic web session and cart data; target is converted (yes/no).",
    "Retail Demand Forecast": "Synthetic store and product observations; target is units_sold.",
    "Delivery ETA Forecast": "Synthetic route and delivery conditions; target is eta_minutes.",
    "Used Vehicle Prices": "Synthetic used-vehicle listing features; target is sale_price.",
}
ALGORITHMS = {
    "classification": [
        {"algorithm": "logistic_regression", "hyperparameters": {"max_iter": 700}},
        {
            "algorithm": "random_forest_classifier",
            "hyperparameters": {"n_estimators": 100, "max_depth": 12},
        },
    ],
    "regression": [
        {"algorithm": "linear_regression", "hyperparameters": {"fit_intercept": True}},
        {
            "algorithm": "random_forest_regressor",
            "hyperparameters": {"n_estimators": 100, "max_depth": 12},
        },
    ],
}


class AtlasAPI:
    def __init__(self, base_url: str, email: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        parsed_base_url = urllib.parse.urlsplit(self.base_url)
        if parsed_base_url.scheme not in {"http", "https"} or not parsed_base_url.netloc:
            raise ValueError("Atlas API base URL must use http or https.")
        self.token: str | None = None
        result = self.request("POST", "/auth/login", {"email": email, "password": password})
        self.token = result["access_token"]

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        fields: dict[str, str] | None = None,
        upload: Path | None = None,
    ) -> Any:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        body: bytes | None = None
        if upload is not None:
            boundary = f"----atlas-{uuid.uuid4().hex}"
            chunks: list[bytes] = []
            for name, value in (fields or {}).items():
                chunks.extend(
                    [
                        f"--{boundary}\r\n".encode(),
                        f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                        value.encode("utf-8"),
                        b"\r\n",
                    ]
                )
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode(),
                    f'Content-Disposition: form-data; name="file"; filename="{upload.name}"\r\n'.encode(),
                    b"Content-Type: text/csv\r\n\r\n",
                    upload.read_bytes(),
                    b"\r\n",
                    f"--{boundary}--\r\n".encode(),
                ]
            )
            body = b"".join(chunks)
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(  # noqa: S310 - uses validated HTTP(S) base URL
            f"{self.base_url}{path}", data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(  # noqa: S310 - base URL is restricted to HTTP(S)
                request, timeout=90
            ) as response:
                content = response.read()
                return json.loads(content) if content else None
        except urllib.error.HTTPError as error:
            response_body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"{method} {path} returned HTTP {error.code}: {response_body}"
            ) from error


def _ensure_project(api: AtlasAPI) -> tuple[str, str]:
    workspaces = api.request("GET", "/workspaces")
    workspace = next((item for item in workspaces if item["name"] == "Demo Workspace"), None)
    if workspace is None:
        if not workspaces:
            raise RuntimeError("The logged-in user has no workspace to hold benchmark data.")
        workspace = workspaces[0]
    projects = api.request("GET", f"/workspaces/{workspace['id']}/projects")
    project = next((item for item in projects if item["name"] == PROJECT_NAME), None)
    if project is None:
        project = api.request(
            "POST",
            f"/workspaces/{workspace['id']}/projects",
            {
                "name": PROJECT_NAME,
                "description": "Synthetic benchmarks for testing Atlas preprocessing, training, and experiment comparison.",
            },
        )
        print(f"Created project: {PROJECT_NAME}")
    else:
        print(f"Using project: {PROJECT_NAME}")
    return workspace["id"], project["id"]


def _ensure_datasets(api: AtlasAPI, project_id: str) -> dict[str, dict[str, Any]]:
    response = api.request(
        "GET",
        "/datasets?" + urllib.parse.urlencode({"project_id": project_id, "page_size": 100}),
    )
    existing = {item["name"]: item for item in response["items"]}
    versions: dict[str, dict[str, Any]] = {}
    for name, filename, _seed, builder in DATASETS:
        _frame, target, problem_type = builder(_seed)
        item = existing.get(name)
        if item and item.get("latest_version_id"):
            detail = api.request("GET", f"/datasets/{item['id']}")
            version = detail["latest_version"]
            print(f"Dataset ready: {name} v{version['version']} (already uploaded)")
        else:
            version = api.request(
                "POST",
                "/datasets",
                fields={
                    "project_id": project_id,
                    "name": name,
                    "description": DESCRIPTIONS[name],
                },
                upload=DATA_DIR / filename,
            )
            print(
                f"Uploaded {name} v{version['version']}: "
                f"{version['row_count']:,} rows, {version['column_count']} columns, "
                f"status={version['status']}"
            )
        versions[name] = {
            "name": name,
            "filename": filename,
            "target": target,
            "problem_type": problem_type,
            "dataset_id": version["dataset_id"],
            "dataset_version_id": version["id"],
            "version": version["version"],
            "row_count": version["row_count"],
            "column_count": version["column_count"],
            "profile": version.get("profile", {}),
            "validation": version.get("validation", {}),
        }
    return versions


def _train_one(api: AtlasAPI, project_id: str, dataset: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "project_id": project_id,
        "dataset_version_id": dataset["dataset_version_id"],
        "name": f"{dataset['name']} - holdout and 3-fold CV",
        "problem_type": dataset["problem_type"],
        "target_column": dataset["target"],
        "test_size": 0.2,
        "random_seed": 42,
        "cv_folds": 3,
        "algorithms": ALGORITHMS[dataset["problem_type"]],
    }
    job = api.request("POST", "/training-jobs", payload)
    job_id = job["id"]
    print(f"Training {dataset['name']}: job {job_id}")
    deadline = time.monotonic() + 1_200
    last_progress: tuple[str, int] | None = None
    while time.monotonic() < deadline:
        job = api.request("GET", f"/training-jobs/{job_id}")
        state = (job["status"], int(job.get("progress", 0)))
        if state != last_progress:
            print(f"  {state[0]} {state[1]}%: {job.get('status_message') or ''}")
            last_progress = state
        if state[0] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(2)
    else:
        raise TimeoutError(f"Training job {job_id} did not finish in 20 minutes.")

    result: dict[str, Any] = {
        "dataset": dataset,
        "job": {key: job.get(key) for key in ("id", "name", "status", "progress", "error_message")},
        "experiments": [],
        "comparison": None,
    }
    if job["status"] != "completed":
        return result

    experiments = [api.request("GET", f"/experiments/{item['id']}") for item in job["experiments"]]
    result["experiments"] = experiments
    if len(experiments) >= 2:
        result["comparison"] = api.request(
            "POST",
            "/experiments/compare",
            {"experiment_ids": [item["id"] for item in experiments]},
        )
    for experiment in experiments:
        metrics = experiment.get("metrics", {})
        print(
            f"  {experiment['algorithm_label']}: "
            f"status={experiment['status']}, metrics={json.dumps(metrics, sort_keys=True)}"
        )
    return result


def _write_reports(results: list[dict[str, Any]], datasets: dict[str, dict[str, Any]]) -> None:
    (DATA_DIR / "benchmark_results.json").write_text(
        json.dumps({"project": PROJECT_NAME, "datasets": datasets, "runs": results}, indent=2),
        encoding="utf-8",
    )
    metric_keys = sorted(
        {
            key
            for run in results
            for experiment in run["experiments"]
            for key in experiment.get("metrics", {})
        }
    )
    with (DATA_DIR / "benchmark_results.csv").open("w", newline="", encoding="utf-8") as file:
        columns = [
            "dataset",
            "problem_type",
            "target",
            "algorithm",
            "status",
            "experiment_id",
            "training_duration_seconds",
            "metrics_json",
            "cv_metrics_json",
            "error_message",
            *metric_keys,
        ]
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for run in results:
            dataset = run["dataset"]
            for experiment in run["experiments"]:
                metrics = experiment.get("metrics", {})
                writer.writerow(
                    {
                        "dataset": dataset["name"],
                        "problem_type": dataset["problem_type"],
                        "target": dataset["target"],
                        "algorithm": experiment.get("algorithm_label", experiment.get("algorithm")),
                        "status": experiment.get("status"),
                        "experiment_id": experiment.get("id"),
                        "training_duration_seconds": experiment.get("training_duration_seconds"),
                        "metrics_json": json.dumps(metrics, sort_keys=True),
                        "cv_metrics_json": json.dumps(experiment.get("cv_metrics"), sort_keys=True),
                        "error_message": experiment.get("error_message"),
                        **{key: metrics.get(key) for key in metric_keys},
                    }
                )

    lines = [
        "# Atlas synthetic benchmark results",
        "",
        f"Project: **{PROJECT_NAME}**",
        "",
        (
            "Each dataset was split once into 80% training and 20% holdout data. "
            "The training job also ran 3-fold cross-validation, with preprocessing fit within each fold."
        ),
        "",
        "Classification models are compared primarily by weighted F1; regression models by RMSE.",
        "",
        "| Dataset | Task | Algorithm | Status | Holdout metrics | CV metrics |",
        "|---|---|---|---|---|---|",
    ]
    primary = {"classification": "f1_weighted", "regression": "rmse"}
    for run in results:
        dataset = run["dataset"]
        experiments = run["experiments"]
        metric = primary[dataset["problem_type"]]
        direction = -1 if dataset["problem_type"] == "classification" else 1
        experiments = sorted(
            experiments,
            key=lambda item: (
                item.get("metrics", {}).get(metric) is None,
                item.get("metrics", {}).get(metric, 0) * direction,
            ),
        )
        for experiment in experiments:
            values = experiment.get("metrics", {})
            cv = experiment.get("cv_metrics") or {}
            compact = ", ".join(
                f"{key}={value:.4f}" if isinstance(value, (int, float)) else f"{key}={value}"
                for key, value in sorted(values.items())
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            )
            cv_compact = (
                ", ".join(
                    f"{key}={value:.4f}" if isinstance(value, (int, float)) else f"{key}={value}"
                    for key, value in sorted(cv.items())
                    if isinstance(value, (int, float)) and not isinstance(value, bool)
                )
                or "not available"
            )
            lines.append(
                f"| {dataset['name']} | {dataset['problem_type']} | "
                f"{experiment.get('algorithm_label', experiment.get('algorithm'))} | "
                f"{experiment.get('status')} | {compact} | {cv_compact} |"
            )
    lines.extend(
        [
            "",
            "All data in this benchmark is synthetic. Treat scores as pipeline checks, not as estimates of production performance.",
            "",
        ]
    )
    (DATA_DIR / "benchmark_summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-base",
        default=os.getenv("ATLAS_API_BASE", "http://127.0.0.1:8000/api/v1"),
    )
    parser.add_argument("--email", default=os.getenv("ATLAS_EMAIL", "demo@atlasmlops.dev"))
    parser.add_argument("--password", default=os.getenv("ATLAS_PASSWORD", "demo-password-123"))
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Regenerate CSV and Markdown reports from the most recent JSON results.",
    )
    args = parser.parse_args()

    results_path = DATA_DIR / "benchmark_results.json"
    if args.report_only:
        if not results_path.exists():
            raise SystemExit("No benchmark_results.json found to rebuild reports from.")
        existing = json.loads(results_path.read_text(encoding="utf-8"))
        _write_reports(existing["runs"], existing["datasets"])
        print(f"Updated reports under {DATA_DIR}")
        return

    if not all((DATA_DIR / filename).exists() for _name, filename, _seed, _builder in DATASETS):
        generate()
    api = AtlasAPI(args.api_base, args.email, args.password)
    _workspace_id, project_id = _ensure_project(api)
    datasets = _ensure_datasets(api, project_id)
    runs = [_train_one(api, project_id, datasets[name]) for name, *_rest in DATASETS]
    _write_reports(runs, datasets)
    failures = [run for run in runs if run["job"]["status"] != "completed"]
    print(f"Saved reports under {DATA_DIR}")
    if failures:
        raise SystemExit(f"{len(failures)} training job(s) did not complete successfully.")
    print(
        f"Completed {sum(len(run['experiments']) for run in runs)} experiments across {len(runs)} datasets."
    )


if __name__ == "__main__":
    main()
