from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
os.environ.setdefault("MLFLOW_DISABLE_TELEMETRY", "true")


class MLflowTracker:
    """Thin, failure-isolated wrapper around MLflow.

    Training must not fail when tracking is unavailable; callers receive a warning
    string and the experiment row records that tracking was degraded.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._mlflow = None

    @property
    def enabled(self) -> bool:
        return self.settings.mlflow_enabled

    def _client(self):
        if self._mlflow is None:
            import mlflow

            self._mlflow = mlflow
        return self._mlflow

    def _ensure_experiment(self, name: str) -> str:
        mlflow = self._client()
        existing = mlflow.get_experiment_by_name(name)
        if existing is not None:
            return existing.experiment_id
        artifact_location = None
        if not self.settings.mlflow_tracking_uri.startswith(("http://", "https://")):
            artifact_root = Path(self.settings.mlflow_artifact_root).resolve()
            artifact_root.mkdir(parents=True, exist_ok=True)
            artifact_location = artifact_root.as_uri()
        return mlflow.create_experiment(name, artifact_location=artifact_location)

    def log_run(
        self,
        *,
        experiment_name: str,
        run_name: str,
        params: dict[str, Any],
        metrics: dict[str, Any],
        tags: dict[str, Any],
        artifact_paths: list[Path],
        model_pipeline: Any | None = None,
        input_example: Any | None = None,
    ) -> tuple[str | None, str | None]:
        if not self.enabled:
            return None, "MLflow tracking is disabled."
        try:
            mlflow = self._client()
            mlflow.set_tracking_uri(self.settings.mlflow_tracking_uri)
            self._ensure_experiment(experiment_name)
            mlflow.set_experiment(experiment_name)
            with mlflow.start_run(
                run_name=run_name, tags={k: str(v) for k, v in tags.items()}
            ) as run:
                flat_params = {
                    key: value
                    for key, value in params.items()
                    if isinstance(value, (str, int, float, bool))
                }
                if flat_params:
                    mlflow.log_params(flat_params)
                numeric_metrics = {
                    key: float(value)
                    for key, value in metrics.items()
                    if isinstance(value, (int, float)) and not isinstance(value, bool)
                }
                if numeric_metrics:
                    mlflow.log_metrics(numeric_metrics)
                for path in artifact_paths:
                    if path.exists():
                        mlflow.log_artifact(str(path))
                if model_pipeline is not None:
                    try:
                        mlflow.sklearn.log_model(
                            model_pipeline,
                            name="model",
                            input_example=input_example,
                            serialization_format="cloudpickle",
                        )
                    except TypeError:
                        mlflow.sklearn.log_model(
                            model_pipeline,
                            artifact_path="model",
                            input_example=input_example,
                            serialization_format="cloudpickle",
                        )
                return run.info.run_id, None
        except Exception as exc:  # tracking is best-effort by design
            message = str(exc).splitlines()[0][:300] or exc.__class__.__name__
            logger.warning("MLflow logging failed", extra={"error": message})
            return None, f"MLflow tracking unavailable: {message}"


def format_tracking_tags(
    job_id: str, project_id: str, dataset_version_id: str, problem_type: str
) -> dict[str, str]:
    return {
        "atlas.job_id": job_id,
        "atlas.project_id": project_id,
        "atlas.dataset_version_id": dataset_version_id,
        "atlas.problem_type": problem_type,
    }
