from __future__ import annotations

import math
from collections import Counter
from typing import Any

import numpy as np
from scipy import stats

from app.ml.utils import float_or_none, json_safe

EPSILON = 1e-6
CONCEPT_MIN_LABELS = 10


def population_stability_index(
    reference: list[float], current: list[float], epsilon: float = EPSILON
) -> float:
    if len(reference) != len(current):
        raise ValueError("PSI inputs must have the same number of buckets")
    if not reference:
        return 0.0
    psi = 0.0
    for ref_share, cur_share in zip(reference, current, strict=True):
        ref_value = max(float(ref_share), epsilon)
        cur_value = max(float(cur_share), epsilon)
        psi += (ref_value - cur_value) * math.log(ref_value / cur_value)
    return float(psi)


def _numeric_edge_buckets(values: np.ndarray, edges: list[Any]) -> tuple[list[float], list[float]]:
    if not edges:
        if values.size == 0:
            return [1.0], [0.0]
        return [1.0], [float(values.size)]
    parsed_edges: list[float] = []
    for idx, edge in enumerate(edges):
        if edge is None or edge == "-inf" or edge == "-Infinity":
            parsed_edges.append(-np.inf if idx == 0 else np.inf)
        elif edge == "inf" or edge == "Infinity":
            parsed_edges.append(np.inf)
        else:
            try:
                parsed_edges.append(float(edge))
            except (ValueError, TypeError):
                parsed_edges.append(-np.inf if idx == 0 else np.inf)
    edge_array = np.asarray(parsed_edges, dtype=float)
    if edge_array.size < 2:
        if values.size == 0:
            return [1.0], [0.0]
        edge_array = np.array([-np.inf, np.inf])
    counts, _ = np.histogram(values, bins=edge_array)
    total = counts.sum()
    proportions = counts / total if total else np.zeros(len(counts), dtype=float)
    return [float(value) for value in proportions], [float(value) for value in counts]


def _categorical_buckets(
    values: list[str], reference_categories: list[str]
) -> tuple[list[float], list[float], list[float]]:
    counter = Counter(values)
    total = sum(counter.values())
    shares: list[float] = []
    counts: list[float] = []
    for category in reference_categories:
        count = counter.get(category, 0)
        counts.append(float(count))
        shares.append(float(count / total) if total else 0.0)
    known = set(reference_categories)
    other = sum(count for value, count in counter.items() if value not in known)
    counts.append(float(other))
    shares.append(float(other / total) if total else 0.0)
    return shares, counts, [float(other)]


def _analyze_numeric_feature(
    name: str,
    reference: dict[str, Any],
    values: list[float],
    missing_rate: float,
    psi_threshold: float,
) -> dict[str, Any]:
    edges = reference.get("bin_edges") or []
    ref_props = list(reference.get("bin_proportions") or [])
    current_values = np.asarray(values, dtype=float)
    current_props, counts = _numeric_edge_buckets(current_values, edges)
    ref_missing = float(reference.get("missing_rate") or 0.0)
    ref_total = sum(ref_props)
    if ref_total > 0:
        ref_props = [value / ref_total * (1 - ref_missing) for value in ref_props]
    current_total = sum(current_props)
    if current_total > 0:
        current_props = [value / current_total * (1 - missing_rate) for value in current_props]
    ref_props = [*ref_props, ref_missing]
    current_props = [*current_props, missing_rate]
    psi = population_stability_index(ref_props, current_props)
    ks_statistic: float | None = None
    ks_pvalue: float | None = None
    ref_samples = reference.get("samples") or []
    if len(values) >= 5 and len(ref_samples) >= 5:
        try:
            result = stats.ks_2samp(np.asarray(ref_samples, dtype=float), current_values)
            ks_statistic = float(result.statistic)
            ks_pvalue = float(result.pvalue)
        except ValueError:
            ks_statistic = None
            ks_pvalue = None
    return {
        "feature": name,
        "kind": "numeric",
        "psi": psi,
        "drifted": psi >= psi_threshold,
        "ks_statistic": ks_statistic,
        "ks_pvalue": ks_pvalue,
        "missing_rate": missing_rate,
        "reference_missing_rate": ref_missing,
        "current_count": len(values),
        "reference_mean": reference.get("mean"),
        "current_mean": float_or_none(np.mean(current_values)) if current_values.size else None,
        "bin_counts": counts,
    }


def _analyze_categorical_feature(
    name: str,
    reference: dict[str, Any],
    values: list[str],
    missing_rate: float,
    psi_threshold: float,
) -> dict[str, Any]:
    reference_distribution: dict[str, float] = reference.get("categories") or {}
    other_reference = float(reference_distribution.get("__other__", 0.0))
    categories = [key for key in reference_distribution if key != "__other__"]
    ref_shares = [float(reference_distribution[key]) for key in categories]
    ref_shares.append(other_reference)
    current_shares, counts, _other = _categorical_buckets(values, categories)
    ref_missing = float(reference.get("missing_rate") or 0.0)
    ref_total = sum(ref_shares)
    if ref_total > 0:
        ref_shares = [value / ref_total * (1 - ref_missing) for value in ref_shares]
    current_total = sum(current_shares)
    if current_total > 0:
        current_shares = [value / current_total * (1 - missing_rate) for value in current_shares]
    ref_shares = [*ref_shares, ref_missing]
    current_shares = [*current_shares, missing_rate]
    psi = population_stability_index(ref_shares, current_shares)
    current_top = Counter(values).most_common(5)
    return {
        "feature": name,
        "kind": "categorical",
        "psi": psi,
        "drifted": psi >= psi_threshold,
        "ks_statistic": None,
        "ks_pvalue": None,
        "missing_rate": missing_rate,
        "reference_missing_rate": ref_missing,
        "current_count": len(values),
        "current_top": [{"value": value, "count": count} for value, count in current_top],
        "bin_counts": counts,
    }


def _analyze_prediction_drift(
    reference: dict[str, Any], predictions: list[Any], psi_threshold: float
) -> dict[str, Any]:
    if not reference or not predictions:
        return {
            "detected": False,
            "psi": 0.0,
            "reason": "No prediction reference or recent predictions.",
            "kind": reference.get("kind") if reference else None,
        }
    kind = reference.get("kind")
    if kind == "numeric":
        edges = reference.get("quantiles") or []
        ref_samples = np.asarray(reference.get("samples") or [], dtype=float)
        numeric_predictions = []
        for value in predictions:
            try:
                numeric_predictions.append(float(value))
            except (TypeError, ValueError):
                continue
        if ref_samples.size == 0 or not numeric_predictions:
            return {"detected": False, "psi": 0.0, "reason": "Insufficient prediction reference."}
        edge_array = np.unique(np.asarray(edges, dtype=float))
        if edge_array.size < 2:
            edge_array = np.array([ref_samples.min() - 0.5, ref_samples.max() + 0.5])
        ref_counts, _ = np.histogram(ref_samples, bins=edge_array)
        cur_counts, _ = np.histogram(np.asarray(numeric_predictions, dtype=float), bins=edge_array)
        ref_props = ref_counts / ref_counts.sum() if ref_counts.sum() else np.zeros_like(ref_counts)
        cur_props = cur_counts / cur_counts.sum() if cur_counts.sum() else np.zeros_like(cur_counts)
        psi = population_stability_index(ref_props.tolist(), cur_props.tolist())
        ks_pvalue = None
        ks_statistic = None
        if len(numeric_predictions) >= 5:
            try:
                result = stats.ks_2samp(ref_samples, np.asarray(numeric_predictions, dtype=float))
                ks_statistic = float(result.statistic)
                ks_pvalue = float(result.pvalue)
            except ValueError:
                pass
        return {
            "detected": psi >= psi_threshold,
            "psi": psi,
            "ks_statistic": ks_statistic,
            "ks_pvalue": ks_pvalue,
            "kind": "numeric",
            "current_mean": float_or_none(np.mean(numeric_predictions)),
            "reference_mean": float_or_none(ref_samples.mean()),
        }

    distribution: dict[str, float] = reference.get("distribution") or {}
    labels = [str(json_safe(value)) for value in predictions]
    current_counter = Counter(labels)
    total = sum(current_counter.values())
    reference_categories = list(distribution.keys())
    ref_shares = [float(distribution[key]) for key in reference_categories]
    current_shares = [
        float(current_counter.get(category, 0) / total) if total else 0.0
        for category in reference_categories
    ]
    known = set(reference_categories)
    other_current = sum(count for value, count in current_counter.items() if value not in known)
    ref_shares.append(max(0.0, 1 - sum(ref_shares)))
    current_shares.append(float(other_current / total) if total else 0.0)
    psi = population_stability_index(ref_shares, current_shares)
    return {
        "detected": psi >= psi_threshold,
        "psi": psi,
        "kind": "categorical",
        "current_distribution": {
            value: float(count / total) for value, count in current_counter.most_common(20)
        }
        if total
        else {},
        "reference_distribution": distribution,
    }


def _analyze_concept_drift(
    samples: list[dict[str, Any]],
    problem_type: str,
    baseline_metrics: dict[str, Any],
    degradation_threshold: float,
) -> tuple[bool, dict[str, Any]]:
    labeled = [
        sample
        for sample in samples
        if sample.get("actual") is not None and sample.get("status") == "success"
    ]
    if len(labeled) < CONCEPT_MIN_LABELS:
        return False, {
            "detected": False,
            "available": False,
            "labels": len(labeled),
            "reason": f"Ground-truth labels are required ({len(labeled)} available, 10 minimum).",
        }

    performance: dict[str, Any] = {"labels": len(labeled)}
    degradation = 0.0
    if problem_type == "classification":
        from sklearn.metrics import accuracy_score, f1_score

        actuals = [json_safe(sample["actual"]) for sample in labeled]
        predicted = [json_safe(sample["prediction"]) for sample in labeled]
        accuracy = float(accuracy_score(actuals, predicted))
        f1 = float(f1_score(actuals, predicted, average="weighted", zero_division=0))
        performance.update({"accuracy": accuracy, "f1_weighted": f1})
        baseline = float_or_none(baseline_metrics.get("accuracy")) or 0.0
        if baseline > 0:
            degradation = (baseline - accuracy) / abs(baseline)
        elif accuracy < 1.0:
            degradation = 1.0
        performance["baseline_accuracy"] = baseline
    else:
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

        actuals = np.asarray([float(sample["actual"]) for sample in labeled], dtype=float)
        predicted = np.asarray([float(sample["prediction"]) for sample in labeled], dtype=float)
        rmse = float(np.sqrt(mean_squared_error(actuals, predicted)))
        mae = float(mean_absolute_error(actuals, predicted))
        r2 = float_or_none(r2_score(actuals, predicted))
        performance.update({"rmse": rmse, "mae": mae, "r2": r2})
        baseline_rmse = float_or_none(baseline_metrics.get("rmse")) or 0.0
        if baseline_rmse > 0:
            degradation = (rmse - baseline_rmse) / abs(baseline_rmse)
        performance["baseline_rmse"] = baseline_rmse

    performance["degradation"] = float(degradation)
    performance["baseline_metrics"] = baseline_metrics
    detected = degradation > degradation_threshold
    return detected, {
        "detected": detected,
        "available": True,
        "labels": len(labeled),
        "reason": (
            f"Performance degraded {degradation * 100:.1f}% versus baseline."
            if detected
            else "Labeled performance is within the configured threshold."
        ),
        "performance": performance,
    }


def analyze_drift(
    reference_profile: dict[str, Any],
    samples: list[dict[str, Any]],
    problem_type: str,
    config: dict[str, Any],
    window_hours: int,
) -> dict[str, Any]:
    psi_threshold = float(config.get("psi_threshold", 0.2))
    drift_share_threshold = float(config.get("drift_share_threshold", 0.3))
    degradation_threshold = float(config.get("performance_degradation_threshold", 0.15))
    min_samples = int(config.get("min_samples", 30))
    sample_count = len(samples)
    successful = [sample for sample in samples if sample.get("status") == "success"]

    if not reference_profile or not reference_profile.get("features"):
        return {
            "status": "insufficient_data",
            "sample_count": sample_count,
            "labeled_count": sum(1 for sample in samples if sample.get("actual") is not None),
            "data_drift_detected": False,
            "prediction_drift_detected": False,
            "concept_drift_detected": False,
            "drift_share": 0.0,
            "psi_max": 0.0,
            "ks_min_pvalue": None,
            "details": {
                "reason": "The model version has no drift reference profile.",
                "window_hours": window_hours,
                "thresholds": config,
            },
        }

    if sample_count < min_samples:
        return {
            "status": "insufficient_data",
            "sample_count": sample_count,
            "labeled_count": sum(1 for sample in samples if sample.get("actual") is not None),
            "data_drift_detected": False,
            "prediction_drift_detected": False,
            "concept_drift_detected": False,
            "drift_share": 0.0,
            "psi_max": 0.0,
            "ks_min_pvalue": None,
            "details": {
                "reason": f"{sample_count} predictions in the window; {min_samples} required.",
                "window_hours": window_hours,
                "thresholds": config,
                "features": [],
            },
        }

    with_features = [sample for sample in successful if sample.get("features")]
    warnings: list[str] = []
    coverage = len(with_features) / len(successful) if successful else 0.0
    if coverage < 1.0:
        warnings.append(
            f"Only {coverage * 100:.1f}% of successful predictions had stored features; drift uses those rows."
        )

    feature_results: list[dict[str, Any]] = []
    reference_features: dict[str, dict[str, Any]] = reference_profile.get("features") or {}
    for name, reference in reference_features.items():
        kind = reference.get("kind")
        if kind == "numeric":
            values = []
            missing = 0
            for sample in with_features:
                record = sample.get("features") or {}
                if name not in record or record[name] is None:
                    missing += 1
                    continue
                try:
                    numeric = float(record[name])
                    if math.isfinite(numeric):
                        values.append(numeric)
                    else:
                        missing += 1
                except (TypeError, ValueError):
                    missing += 1
            missing_rate = missing / len(with_features) if with_features else 0.0
            feature_results.append(
                _analyze_numeric_feature(name, reference, values, missing_rate, psi_threshold)
            )
        else:
            values = []
            missing = 0
            for sample in with_features:
                record = sample.get("features") or {}
                raw = record.get(name)
                if raw is None:
                    missing += 1
                    continue
                values.append(str(json_safe(raw)).strip())
            missing_rate = missing / len(with_features) if with_features else 0.0
            feature_results.append(
                _analyze_categorical_feature(name, reference, values, missing_rate, psi_threshold)
            )

    drifted_features = [feature for feature in feature_results if feature["drifted"]]
    drift_share = len(drifted_features) / len(feature_results) if feature_results else 0.0
    data_drift_detected = drift_share >= drift_share_threshold
    prediction_drift = _analyze_prediction_drift(
        reference_profile.get("prediction_reference") or {},
        [sample.get("prediction") for sample in successful],
        psi_threshold,
    )
    concept_detected, concept = _analyze_concept_drift(
        samples,
        problem_type,
        reference_profile.get("baseline_metrics") or {},
        degradation_threshold,
    )

    psi_values = [feature["psi"] for feature in feature_results]
    if prediction_drift.get("psi") is not None:
        psi_values.append(float(prediction_drift["psi"]))
    psi_max = max(psi_values) if psi_values else 0.0
    ks_pvalues = [
        feature["ks_pvalue"] for feature in feature_results if feature.get("ks_pvalue") is not None
    ]
    ks_min = min(ks_pvalues) if ks_pvalues else None

    if concept_detected or data_drift_detected:
        status = "critical"
    elif prediction_drift.get("detected") or drifted_features:
        status = "warning"
    else:
        status = "healthy"

    labeled_count = sum(1 for sample in samples if sample.get("actual") is not None)
    return {
        "status": status,
        "sample_count": sample_count,
        "labeled_count": labeled_count,
        "data_drift_detected": data_drift_detected,
        "prediction_drift_detected": bool(prediction_drift.get("detected")),
        "concept_drift_detected": concept_detected,
        "drift_share": drift_share,
        "psi_max": psi_max,
        "ks_min_pvalue": ks_min,
        "details": {
            "window_hours": window_hours,
            "thresholds": {
                "psi": psi_threshold,
                "drift_share": drift_share_threshold,
                "performance_degradation": degradation_threshold,
                "min_samples": min_samples,
            },
            "features": feature_results,
            "drifted_features": [feature["feature"] for feature in drifted_features],
            "prediction_drift": prediction_drift,
            "concept_drift": concept,
            "warnings": warnings,
            "feature_coverage": coverage,
            "definitions": {
                "data_drift": "Input feature distributions shifted versus the training split.",
                "prediction_drift": "Output distribution shifted versus the held-out baseline.",
                "concept_drift": "Labeled performance degraded versus baseline; requires ground truth.",
            },
        },
    }
