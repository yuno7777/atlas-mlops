from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.ml.preprocessing import PreparedFeatures
from app.ml.utils import float_or_none, json_safe

MAX_REFERENCE_SAMPLES = 2000
NUMERIC_BINS = 10
TOP_CATEGORIES = 20


def _numeric_reference(values: pd.Series) -> dict[str, Any]:
    numeric = pd.to_numeric(values, errors="coerce")
    missing_rate = float(numeric.isna().mean()) if len(values) else 0.0
    non_null = numeric.dropna().to_numpy(dtype=float)
    if non_null.size == 0:
        return {
            "kind": "numeric",
            "bin_edges": [],
            "bin_proportions": [],
            "missing_rate": 1.0,
            "mean": None,
            "std": None,
            "samples": [],
        }
    quantiles = np.linspace(0, 1, NUMERIC_BINS + 1)
    edges = np.unique(np.quantile(non_null, quantiles))
    if edges.size < 2:
        edges = np.array([non_null.min() - 0.5, non_null.max() + 0.5])
    edges = np.concatenate(([-np.inf], edges[1:-1], [np.inf]))
    counts, _ = np.histogram(non_null, bins=edges)
    proportions = counts / counts.sum() if counts.sum() else np.zeros_like(counts, dtype=float)
    sample_size = min(MAX_REFERENCE_SAMPLES, non_null.size)
    if non_null.size > sample_size:
        indices = np.linspace(0, non_null.size - 1, sample_size).astype(int)
        samples = non_null[indices]
    else:
        samples = non_null
    return {
        "kind": "numeric",
        "bin_edges": [float_or_none(edge) for edge in edges],
        "bin_proportions": [float(value) for value in proportions],
        "missing_rate": missing_rate,
        "mean": float_or_none(np.mean(non_null)),
        "std": float_or_none(np.std(non_null)),
        "samples": [float(value) for value in samples],
    }


def _categorical_reference(values: pd.Series) -> dict[str, Any]:
    strings = values.astype("string").str.strip()
    strings = strings.mask(strings == "", pd.NA)
    missing_rate = float(strings.isna().mean()) if len(strings) else 0.0
    non_null = strings.dropna()
    counts = non_null.value_counts()
    total = int(counts.sum())
    top_counts = counts.head(TOP_CATEGORIES)
    categories = (
        {str(category): float(count / total) for category, count in top_counts.items()}
        if total
        else {}
    )
    if total and len(counts) > len(top_counts):
        categories["__other__"] = float((counts.iloc[len(top_counts) :].sum()) / total)
    return {
        "kind": "categorical",
        "categories": categories,
        "missing_rate": missing_rate,
        "unique": int(non_null.nunique()),
    }


def build_reference_profile(
    prepared: PreparedFeatures,
    predictions,
    problem_type: str,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    features: dict[str, Any] = {}
    for column in prepared.frame.columns:
        series = prepared.frame[column]
        if column in prepared.numeric_columns:
            features[column] = _numeric_reference(series)
        else:
            features[column] = _categorical_reference(series)

    prediction_values = pd.Series(predictions)
    if problem_type == "classification":
        value_counts = prediction_values.astype(str).value_counts(normalize=True)
        prediction_reference: dict[str, Any] = {
            "kind": "categorical",
            "distribution": {str(label): float(value) for label, value in value_counts.items()},
        }
    elif problem_type == "regression":
        numeric_predictions = pd.to_numeric(prediction_values, errors="coerce").dropna()
        if numeric_predictions.empty:
            prediction_reference = {"kind": "numeric", "quantiles": [], "samples": []}
        else:
            quantiles = np.quantile(numeric_predictions.to_numpy(), np.linspace(0, 1, 11))
            prediction_reference = {
                "kind": "numeric",
                "quantiles": [float(value) for value in quantiles],
                "samples": [
                    float(value)
                    for value in np.linspace(
                        numeric_predictions.min(),
                        numeric_predictions.max(),
                        min(500, len(numeric_predictions)),
                    )
                ],
            }
    else:
        value_counts = prediction_values.astype(str).value_counts(normalize=True)
        prediction_reference = {
            "kind": "categorical",
            "distribution": {str(label): float(value) for label, value in value_counts.items()},
        }

    return {
        "version": 1,
        "problem_type": problem_type,
        "trained_rows": int(len(prepared.frame)),
        "schema": {"features": prepared.schema},
        "features": features,
        "prediction_reference": prediction_reference,
        "baseline_metrics": {key: json_safe(value) for key, value in metrics.items()},
        "dropped_columns": prepared.dropped_columns,
    }
