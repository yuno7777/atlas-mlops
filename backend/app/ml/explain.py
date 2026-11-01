from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from app.core.exceptions import ValidationError
from app.ml.inference import validate_records
from app.ml.utils import json_safe

BACKGROUND_SAMPLES = 8
PERMUTATIONS = 16


def _evenly_spaced(values: list[Any], limit: int) -> list[Any]:
    if not values:
        return []
    if len(values) <= limit:
        return list(values)
    indices = np.linspace(0, len(values) - 1, limit).astype(int)
    return [values[int(index)] for index in indices]


def _background_records(reference_profile: dict[str, Any]) -> list[dict[str, Any]]:
    features = reference_profile.get("schema", {}).get("features", [])
    summary = reference_profile.get("features", {})
    columns: dict[str, list[Any]] = {}
    for feature in features:
        name = feature["name"]
        stats = summary.get(name) or {}
        kind = stats.get("kind") or feature.get("kind")
        if kind == "numeric":
            values = [value for value in stats.get("samples", []) if value is not None]
            columns[name] = _evenly_spaced(values, BACKGROUND_SAMPLES)
        else:
            categories = [
                category
                for category, weight in (stats.get("categories") or {}).items()
                if category != "__other__" and weight > 0
            ]
            columns[name] = _evenly_spaced(categories, BACKGROUND_SAMPLES)
    width = max((len(values) for values in columns.values()), default=0)
    if width == 0:
        raise ValidationError("The model has no reference samples for explanations.")
    records: list[dict[str, Any]] = []
    for index in range(width):
        record: dict[str, Any] = {}
        for name, values in columns.items():
            if not values:
                raise ValidationError(
                    f"The model reference profile has no values for feature '{name}'."
                )
            record[name] = values[index % len(values)]
        records.append(record)
    return records


def _score_function(
    pipeline: Pipeline, problem_type: str, frame: pd.DataFrame
) -> tuple[Callable[[pd.DataFrame], float], float]:
    if problem_type == "classification":
        predicted = pipeline.predict(frame)
        label = json_safe(predicted[0])
        try:
            classes = list(pipeline.named_steps["model"].classes_)
        except (AttributeError, KeyError):
            classes = None

        def positive_index() -> int:
            if classes is None:
                return 0
            for index, value in enumerate(classes):
                if str(json_safe(value)) == str(label):
                    return index
            return 0

        class_index = positive_index()

        def score(batch: pd.DataFrame) -> float:
            probabilities = pipeline.predict_proba(batch)
            return float(np.mean(probabilities[:, class_index]))

        prediction = float(pipeline.predict_proba(frame)[0, class_index])
        return score, prediction

    if problem_type == "regression":

        def score(batch: pd.DataFrame) -> float:
            return float(np.mean(np.asarray(pipeline.predict(batch), dtype=float)))

        prediction = float(pipeline.predict(frame)[0])
        return score, prediction

    raise ValidationError(
        "Feature explanations are available for classification and regression models."
    )


def explain_record(
    pipeline: Pipeline,
    reference_profile: dict[str, Any],
    problem_type: str,
    record: dict[str, Any],
) -> dict[str, Any]:
    started = time.perf_counter()
    frame = validate_records([record], reference_profile)
    backgrounds = validate_records(_background_records(reference_profile), reference_profile)
    score, prediction = _score_function(pipeline, problem_type, frame)
    baseline = score(backgrounds)
    feature_names = [feature["name"] for feature in reference_profile["schema"]["features"]]
    totals = dict.fromkeys(feature_names, 0.0)
    rng = random.Random(1729)
    for _ in range(PERMUTATIONS):
        order = feature_names[:]
        rng.shuffle(order)
        current = backgrounds.copy()
        previous = score(current)
        for name in order:
            current[name] = frame.iloc[0][name]
            updated = score(current)
            totals[name] += updated - previous
            previous = updated
    contributions = [
        {
            "feature": name,
            "value": json_safe(frame.iloc[0][name]),
            "contribution": round(totals[name] / PERMUTATIONS, 6),
            "direction": (
                "increases" if totals[name] > 0 else "decreases" if totals[name] < 0 else "neutral"
            ),
        }
        for name in feature_names
    ]
    contributions.sort(key=lambda item: abs(item["contribution"]), reverse=True)
    return {
        "problem_type": problem_type,
        "method": "monte_carlo_permutation_shapley",
        "baseline": round(baseline, 6),
        "prediction": round(prediction, 6),
        "contributions": contributions,
        "background_samples": len(backgrounds.index),
        "permutations": PERMUTATIONS,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
    }
