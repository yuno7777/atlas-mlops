from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    calinski_harabasz_score,
    davies_bouldin_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
    silhouette_score,
)

from app.core.exceptions import TrainingError
from app.ml.utils import float_or_none
from app.models.enums import ProblemType

CLASSIFICATION_METRICS = [
    "accuracy",
    "precision_weighted",
    "recall_weighted",
    "f1_weighted",
    "roc_auc",
]
REGRESSION_METRICS = ["rmse", "mae", "r2"]
CLUSTERING_METRICS = ["silhouette", "davies_bouldin", "calinski_harabasz"]

METRIC_DIRECTIONS: dict[str, str] = {
    "accuracy": "max",
    "precision_weighted": "max",
    "recall_weighted": "max",
    "f1_weighted": "max",
    "roc_auc": "max",
    "rmse": "min",
    "mae": "min",
    "r2": "max",
    "silhouette": "max",
    "davies_bouldin": "min",
    "calinski_harabasz": "max",
    "training_duration_seconds": "min",
}

PRIMARY_METRIC: dict[str, str] = {
    ProblemType.CLASSIFICATION: "accuracy",
    ProblemType.REGRESSION: "r2",
    ProblemType.CLUSTERING: "silhouette",
}


def primary_metric(problem_type: str) -> str:
    return PRIMARY_METRIC.get(problem_type, "accuracy")


def metric_directions(problem_type: str) -> dict[str, str]:
    keys = {
        ProblemType.CLASSIFICATION: CLASSIFICATION_METRICS,
        ProblemType.REGRESSION: REGRESSION_METRICS,
        ProblemType.CLUSTERING: CLUSTERING_METRICS,
    }.get(problem_type, [])
    return {key: METRIC_DIRECTIONS[key] for key in keys}


def evaluate_classification(model, X_test, y_test) -> dict[str, float | None]:
    predictions = model.predict(X_test)
    metrics: dict[str, float | None] = {
        "accuracy": float(accuracy_score(y_test, predictions)),
        "precision_weighted": float(
            precision_score(y_test, predictions, average="weighted", zero_division=0)
        ),
        "recall_weighted": float(
            recall_score(y_test, predictions, average="weighted", zero_division=0)
        ),
        "f1_weighted": float(f1_score(y_test, predictions, average="weighted", zero_division=0)),
        "roc_auc": None,
    }
    try:
        probabilities = model.predict_proba(X_test)
        classes = list(model.classes_)
        if len(classes) == 2:
            metrics["roc_auc"] = float(roc_auc_score(y_test, probabilities[:, 1]))
        elif len(classes) > 2:
            metrics["roc_auc"] = float(
                roc_auc_score(
                    y_test,
                    probabilities,
                    multi_class="ovr",
                    average="macro",
                    labels=classes,
                )
            )
    except (AttributeError, ValueError):
        metrics["roc_auc"] = None
    classes = getattr(model, "classes_", None)
    metrics["classes"] = len(classes) if classes is not None else None
    return metrics


def evaluate_regression(model, X_test, y_test) -> dict[str, float | None]:
    predictions = model.predict(X_test)
    rmse = float(np.sqrt(mean_squared_error(y_test, predictions)))
    return {
        "rmse": rmse,
        "mae": float(mean_absolute_error(y_test, predictions)),
        "r2": float_or_none(r2_score(y_test, predictions)),
    }


def evaluate_clustering(preprocessor, clusterer, X_test) -> dict[str, float | None]:
    try:
        transformed = preprocessor.transform(X_test)
        labels = clusterer.predict(transformed)
    except Exception as exc:
        raise TrainingError(f"Clustering evaluation failed: {exc}") from exc
    labels = np.asarray(labels)
    valid = labels[labels >= 0]
    if len(set(valid.tolist())) < 2 or len(valid) < 3:
        raise TrainingError(
            "Clustering produced fewer than two non-noise clusters; adjust hyperparameters."
        )
    mask = labels >= 0
    data = np.asarray(transformed)[mask]
    valid_labels = labels[mask]
    metrics: dict[str, float | None] = {
        "silhouette": float_or_none(silhouette_score(data, valid_labels)),
        "davies_bouldin": float_or_none(davies_bouldin_score(data, valid_labels)),
        "calinski_harabasz": float_or_none(calinski_harabasz_score(data, valid_labels)),
        "clusters": float(len(set(valid_labels.tolist()))),
        "noise_points": float((~mask).sum()),
    }
    return metrics
