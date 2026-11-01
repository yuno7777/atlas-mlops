from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold, StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import Pipeline

from app.core.exceptions import TrainingError
from app.ml.algorithms import AlgorithmSpec, build_estimator
from app.ml.evaluation import (
    evaluate_classification,
    evaluate_clustering,
    evaluate_fairness,
    evaluate_regression,
    primary_metric,
)
from app.ml.preprocessing import (
    PreparedFeatures,
    build_preprocessor,
    coerce_frame_to_schema,
    prepare_training_features,
)
from app.ml.reference import build_reference_profile
from app.ml.utils import json_safe
from app.models.enums import ProblemType

MIN_ROWS = 20
MAX_CLASSES = 50


@dataclass
class TrainingConfig:
    problem_type: str
    target_column: str | None
    feature_columns: list[str] | None
    test_size: float = 0.2
    random_seed: int = 42
    cv_folds: int = 0
    sensitive_columns: list[str] = field(default_factory=list)


@dataclass
class TrainingResult:
    pipeline: Pipeline
    metrics: dict[str, Any]
    cv_metrics: dict[str, Any] | None
    reference_profile: dict[str, Any]
    duration_seconds: float
    train_rows: int
    test_rows: int
    warnings: list[str] = field(default_factory=list)
    feature_count: int = 0


def _resolve_features(df: pd.DataFrame, config: TrainingConfig) -> list[str]:
    if config.feature_columns:
        missing = [column for column in config.feature_columns if column not in df.columns]
        if missing:
            raise TrainingError(f"Feature columns not found in dataset: {', '.join(missing)}")
        if config.target_column and config.target_column in config.feature_columns:
            raise TrainingError("The target column cannot also be a feature.")
        leaked = sorted(set(config.sensitive_columns) & set(config.feature_columns))
        if leaked:
            raise TrainingError(
                "Sensitive audit columns must be excluded from model features: "
                + ", ".join(leaked[:10])
            )
        return list(config.feature_columns)
    excluded = {config.target_column, *config.sensitive_columns}
    return [str(column) for column in df.columns if str(column) not in excluded]


def _prepare_supervised_target(
    df: pd.DataFrame, config: TrainingConfig
) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    if not config.target_column:
        raise TrainingError("A target column is required for supervised training.")
    if config.target_column not in df.columns:
        raise TrainingError(f"Target column '{config.target_column}' not found in the dataset.")
    target = df[config.target_column]
    warnings: list[str] = []
    if config.problem_type == ProblemType.CLASSIFICATION:
        mask = target.notna()
        cleaned = target[mask]
        if cleaned.dtype == object or isinstance(cleaned.dtype, pd.CategoricalDtype):
            cleaned = cleaned.astype(str).str.strip()
            mask = mask & (cleaned != "")
            cleaned = cleaned[mask]
        classes = cleaned.nunique()
        if classes < 2:
            raise TrainingError("The target has fewer than two classes after cleaning.")
        if classes > MAX_CLASSES:
            raise TrainingError(
                f"The target has {classes} distinct values; use regression or reduce cardinality."
            )
        dropped = int((~mask).sum())
        if dropped:
            warnings.append(f"Dropped {dropped} rows with a missing target label.")
        if cleaned.dtype == object:
            cleaned = cleaned.astype(str)
        return df.loc[mask], cleaned, warnings

    numeric_target = pd.to_numeric(target, errors="coerce")
    mask = numeric_target.notna() & np.isfinite(numeric_target.astype(float))
    dropped = int((~mask).sum())
    if dropped:
        warnings.append(f"Dropped {dropped} rows with a missing or non-numeric target.")
    cleaned = numeric_target[mask].astype(float)
    if len(cleaned) < MIN_ROWS:
        raise TrainingError(f"At least {MIN_ROWS} labeled rows are required.")
    return df.loc[mask], cleaned, warnings


def _split(
    features: pd.DataFrame,
    target: pd.Series | None,
    config: TrainingConfig,
    warnings: list[str],
):
    stratify = None
    if config.problem_type == ProblemType.CLASSIFICATION and target is not None:
        counts = target.value_counts()
        if len(counts) > 1 and int(counts.min()) >= 2:
            stratify = target
    try:
        if target is None:
            return train_test_split(
                features,
                test_size=config.test_size,
                random_state=config.random_seed,
            )
        return train_test_split(
            features,
            target,
            test_size=config.test_size,
            random_state=config.random_seed,
            stratify=stratify,
        )
    except ValueError as exc:
        if stratify is not None:
            warnings.append(f"Stratified split failed ({exc}); using a random split.")
            return train_test_split(
                features,
                target,
                test_size=config.test_size,
                random_state=config.random_seed,
            )
        raise TrainingError(f"Could not split the dataset: {exc}") from exc


def _cross_validate(
    pipeline: Pipeline,
    prepared: PreparedFeatures,
    target: pd.Series,
    config: TrainingConfig,
) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    if config.cv_folds < 2:
        return None, warnings
    if config.problem_type == ProblemType.CLASSIFICATION:
        counts = target.value_counts()
        folds = min(config.cv_folds, int(counts.min()))
        if folds < 2:
            warnings.append("Cross-validation skipped: the smallest class has fewer than 2 rows.")
            return None, warnings
        splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=config.random_seed)
        scoring = {
            "accuracy": "accuracy",
            "f1_weighted": "f1_weighted",
            "precision_weighted": "precision_weighted",
            "recall_weighted": "recall_weighted",
            "roc_auc": "roc_auc",
        }
    else:
        folds = config.cv_folds
        splitter = KFold(n_splits=folds, shuffle=True, random_state=config.random_seed)
        scoring = {
            "rmse": "neg_root_mean_squared_error",
            "mae": "neg_mean_absolute_error",
            "r2": "r2",
        }
    try:
        scores = cross_validate(
            pipeline,
            prepared.frame,
            target,
            cv=splitter,
            scoring=scoring,
            n_jobs=1,
            error_score="raise",
        )
    except Exception as exc:
        warnings.append(f"Cross-validation failed: {str(exc).splitlines()[0][:200]}")
        return None, warnings
    result: dict[str, Any] = {"folds": folds}
    for metric in scoring:
        values = np.asarray(scores[f"test_{metric}"], dtype=float)
        if metric in {"rmse", "mae"}:
            values = -values
        result[f"{metric}_mean"] = float(np.mean(values))
        result[f"{metric}_std"] = float(np.std(values))
    return result, warnings


def train_algorithm(
    df: pd.DataFrame,
    spec: AlgorithmSpec,
    hyperparameters: dict[str, Any],
    config: TrainingConfig,
) -> TrainingResult:
    started = time.perf_counter()
    if len(df) < MIN_ROWS:
        raise TrainingError(f"At least {MIN_ROWS} rows are required to train a model.")
    feature_columns = _resolve_features(df, config)
    if len(feature_columns) < 1:
        raise TrainingError("Select at least one feature column.")
    warnings: list[str] = []

    if config.problem_type in {ProblemType.CLASSIFICATION, ProblemType.REGRESSION}:
        cleaned, target, target_warnings = _prepare_supervised_target(df, config)
        warnings.extend(target_warnings)
        features = cleaned[feature_columns]
        split = _split(features, target, config, warnings)
        X_train, X_test, y_train, y_test = split
        audit_groups = cleaned.loc[X_test.index, config.sensitive_columns]
    else:
        target = None
        features = df[feature_columns]
        X_train, X_test = _split(features, None, config, warnings)
        y_train = y_test = None

    if len(X_train) < 3:
        raise TrainingError("The training split is too small after cleaning.")

    prepared = prepare_training_features(X_train)
    warnings.extend(prepared.warnings)
    if not prepared.schema:
        raise TrainingError("No usable features remain after dropping empty columns.")
    preprocessor = build_preprocessor(prepared)
    estimator = build_estimator(spec, hyperparameters, config.random_seed)
    pipeline = Pipeline([("preprocess", preprocessor), ("model", estimator)])

    try:
        pipeline.fit(prepared.frame, y_train)
    except Exception as exc:
        message = str(exc).splitlines()[0][:300] or exc.__class__.__name__
        raise TrainingError(f"{spec.label} failed during training: {message}") from exc

    test_frame = coerce_frame_to_schema(X_test, prepared.schema)
    try:
        if config.problem_type == ProblemType.CLASSIFICATION:
            metrics = evaluate_classification(pipeline, test_frame, y_test)
            predictions = pipeline.predict(test_frame)
            if config.sensitive_columns:
                metrics["fairness"] = evaluate_fairness(
                    y_test, predictions, audit_groups, "classification", pipeline.classes_
                )
        elif config.problem_type == ProblemType.REGRESSION:
            metrics = evaluate_regression(pipeline, test_frame, y_test)
            predictions = pipeline.predict(test_frame)
            if config.sensitive_columns:
                metrics["fairness"] = evaluate_fairness(
                    y_test, predictions, audit_groups, "regression", None
                )
        else:
            metrics = evaluate_clustering(
                pipeline.named_steps["preprocess"], pipeline.named_steps["model"], X_test
            )
            predictions = pipeline.predict(test_frame)
    except TrainingError:
        raise
    except Exception as exc:
        message = str(exc).splitlines()[0][:300] or exc.__class__.__name__
        raise TrainingError(f"{spec.label} failed during evaluation: {message}") from exc

    cv_metrics = None
    if spec.supports_cv and config.cv_folds >= 2 and y_train is not None:
        cv_metrics, cv_warnings = _cross_validate(pipeline, prepared, y_train, config)
        warnings.extend(cv_warnings)

    metrics["test_samples"] = int(len(test_frame))
    metrics["train_samples"] = int(len(prepared.frame))
    metrics["features"] = int(len(prepared.schema))
    metrics = {key: json_safe(value) for key, value in metrics.items()}

    reference_profile = build_reference_profile(prepared, predictions, config.problem_type, metrics)
    duration = time.perf_counter() - started
    reference_profile["primary_metric"] = primary_metric(config.problem_type)
    return TrainingResult(
        pipeline=pipeline,
        metrics=metrics,
        cv_metrics=cv_metrics,
        reference_profile=reference_profile,
        duration_seconds=duration,
        train_rows=int(len(prepared.frame)),
        test_rows=int(len(test_frame)),
        warnings=warnings,
        feature_count=len(prepared.schema),
    )
