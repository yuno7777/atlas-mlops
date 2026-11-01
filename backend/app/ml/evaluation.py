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


def evaluate_fairness(y_true, y_pred, sensitive, problem_type: str, classes) -> dict:
    """Summarize held-out performance by audit group; sensitive columns are never model inputs."""
    if sensitive is None or sensitive.empty:
        return {"status": "not_available", "reason": "No sensitive columns were selected."}
    if len(sensitive) != len(y_true):
        return {"status": "not_available", "reason": "Audit rows do not match evaluation rows."}

    groups: dict[str, dict] = {}
    for column in sensitive.columns:
        values = sensitive[column].astype("string").fillna("<missing>")
        by_group: dict[str, dict] = {}
        selection_rates: list[float] = []
        accuracies: list[float] = []
        errors: list[float] = []
        for group in sorted(values.unique().tolist()):
            mask = values.to_numpy() == group
            count = int(mask.sum())
            if count == 0:
                continue
            group_true = np.asarray(y_true)[mask]
            group_pred = np.asarray(y_pred)[mask]
            item: dict[str, float | int] = {"samples": count}
            if problem_type == "classification":
                positive = classes[-1] if classes is not None and len(classes) == 2 else None
                item["accuracy"] = float(accuracy_score(group_true, group_pred))
                if positive is not None:
                    selection = float(np.mean(group_pred == positive))
                    item["selection_rate"] = selection
                    selection_rates.append(selection)
                    positives = group_true == positive
                    negatives = ~positives
                    item["true_positive_rate"] = (
                        float(np.mean(group_pred[positives] == positive))
                        if positives.any()
                        else 0.0
                    )
                    item["false_positive_rate"] = (
                        float(np.mean(group_pred[negatives] == positive))
                        if negatives.any()
                        else 0.0
                    )
                accuracies.append(float(item["accuracy"]))
            else:
                residual = np.asarray(group_true, dtype=float) - np.asarray(group_pred, dtype=float)
                item["mae"] = float(np.mean(np.abs(residual)))
                item["rmse"] = float(np.sqrt(np.mean(np.square(residual))))
                errors.append(float(item["mae"]))
            by_group[str(group)] = item
        report: dict[str, object] = {
            "groups": by_group,
            "group_count": len(by_group),
            "smallest_group_samples": min(
                (int(item["samples"]) for item in by_group.values()), default=0
            ),
        }
        if problem_type == "classification":
            report["positive_class"] = (
                str(classes[-1]) if classes is not None and len(classes) == 2 else None
            )
            report["selection_rate_gap"] = (
                round(max(selection_rates) - min(selection_rates), 6)
                if len(selection_rates) > 1
                else None
            )
            report["accuracy_gap"] = (
                round(max(accuracies) - min(accuracies), 6) if len(accuracies) > 1 else None
            )
        else:
            report["mae_gap"] = round(max(errors) - min(errors), 6) if len(errors) > 1 else None
        groups[column] = report

    return {
        "status": "evaluated",
        "method": "held-out subgroup metrics",
        "sensitive_columns": list(sensitive.columns),
        "notes": [
            "Group metrics are descriptive, not proof of fairness.",
            "For classification, selection-rate and TPR/FPR metrics use the final class only for binary targets.",
            "Small groups can produce unstable estimates; inspect group sample counts.",
        ],
        "features_excluded": list(sensitive.columns),
        "columns": groups,
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
