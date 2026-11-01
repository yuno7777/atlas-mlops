from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from app.core.exceptions import ValidationError
from app.ml.utils import json_safe


def _schema_features(reference_profile: dict[str, Any]) -> list[dict[str, Any]]:
    schema = reference_profile.get("schema", {}) if reference_profile else {}
    features = schema.get("features", [])
    if not features:
        raise ValidationError("The registered model has no feature schema.", status_code=503)
    return features


def validate_records(
    records: list[dict[str, Any]], reference_profile: dict[str, Any]
) -> pd.DataFrame:
    features = _schema_features(reference_profile)
    expected = [feature["name"] for feature in features]
    expected_set = set(expected)
    errors: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append({"field": f"records[{index}]", "message": "Record must be an object"})
            continue
        unknown = sorted(set(record) - expected_set)
        missing = [name for name in expected if name not in record]
        if unknown:
            errors.append(
                {
                    "field": f"records[{index}]",
                    "message": f"Unknown fields: {', '.join(unknown[:10])}",
                }
            )
        if missing:
            errors.append(
                {
                    "field": f"records[{index}]",
                    "message": f"Missing required fields: {', '.join(missing[:10])}",
                }
            )
        if unknown or missing:
            continue
        row: dict[str, Any] = {}
        for feature in features:
            name = feature["name"]
            value = record[name]
            if isinstance(value, (dict, list, tuple, set)):
                errors.append(
                    {
                        "field": f"records[{index}].{name}",
                        "message": "Nested values are not supported for tabular features",
                    }
                )
                continue
            if value is None or (isinstance(value, float) and math.isnan(value)):
                row[name] = np.nan
                continue
            if feature["kind"] == "numeric":
                if isinstance(value, bool):
                    row[name] = 1.0 if value else 0.0
                    continue
                try:
                    numeric_value = float(value)
                except (TypeError, ValueError):
                    errors.append(
                        {
                            "field": f"records[{index}].{name}",
                            "message": "Expected a numeric value",
                        }
                    )
                    continue
                if not math.isfinite(numeric_value):
                    errors.append(
                        {
                            "field": f"records[{index}].{name}",
                            "message": "Numeric values must be finite",
                        }
                    )
                    continue
                row[name] = numeric_value
            else:
                if isinstance(value, bool):
                    row[name] = "true" if value else "false"
                else:
                    text = str(value).strip()
                    row[name] = np.nan if text == "" else text
        rows.append(row)

    if errors:
        raise ValidationError(
            f"{len(errors)} validation error(s) in prediction input.", details=errors[:50]
        )
    frame = pd.DataFrame(rows, columns=expected)
    for feature in features:
        if feature["kind"] == "numeric":
            frame[feature["name"]] = pd.to_numeric(frame[feature["name"]], errors="coerce")
        else:
            frame[feature["name"]] = frame[feature["name"]].astype(object)
    return frame


def run_predictions(
    pipeline: Pipeline, problem_type: str, frame: pd.DataFrame
) -> list[dict[str, Any]]:
    try:
        predictions = pipeline.predict(frame)
    except Exception as exc:
        message = str(exc).splitlines()[0][:300] or exc.__class__.__name__
        raise ValidationError(f"The model could not score this input: {message}") from exc

    probabilities: np.ndarray | None = None
    if problem_type == "classification":
        try:
            probabilities = pipeline.predict_proba(frame)
        except (AttributeError, ValueError):
            probabilities = None

    results: list[dict[str, Any]] = []
    for index, prediction in enumerate(predictions):
        item: dict[str, Any] = {"prediction": json_safe(prediction)}
        if probabilities is not None:
            try:
                classes = pipeline.named_steps["model"].classes_
            except (AttributeError, KeyError):
                classes = range(probabilities.shape[1])
            item["probabilities"] = {
                str(json_safe(label)): float(value)
                for label, value in zip(classes, probabilities[index], strict=False)
            }
        else:
            item["probabilities"] = None
        results.append(item)
    return results
