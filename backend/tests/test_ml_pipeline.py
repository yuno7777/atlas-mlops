from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.core.exceptions import DatasetValidationError, ValidationError
from app.ml.algorithms import get_algorithm, list_algorithms, validate_hyperparameters
from app.ml.drift import population_stability_index
from app.ml.profiling import profile_dataframe, suggest_targets
from app.ml.training import TrainingConfig, train_algorithm
from app.ml.validation import normalize_extension, read_dataframe, sniff_file


def test_validation_rejects_unsupported_extension():
    with pytest.raises(DatasetValidationError):
        normalize_extension("data.exe")


def test_validation_rejects_empty(tmp_path: Path):
    empty_file = tmp_path / "empty.csv"
    empty_file.write_bytes(b"")
    with pytest.raises(DatasetValidationError):
        sniff_file(empty_file, ".csv")


def test_validation_reads_valid_csv(tmp_path: Path):
    csv_file = tmp_path / "valid.csv"
    csv_file.write_bytes(b"col1,col2,target\n1,a,0\n2,b,1\n3,c,0\n")
    df = read_dataframe(csv_file, "valid.csv")
    assert len(df) == 3
    assert list(df.columns) == ["col1", "col2", "target"]


def test_profiling_and_target_suggestions():
    df = pd.DataFrame(
        {
            "num1": [1.0, 2.0, 3.0, 4.0, 5.0, np.nan],
            "cat1": ["a", "b", "a", "b", "c", "a"],
            "target_class": [0, 1, 0, 1, 0, 1],
            "target_reg": [10.5, 20.3, 30.1, 40.8, 50.2, 60.0],
        }
    )
    profile = profile_dataframe(df)
    assert profile["rows"] == 6
    assert profile["columns"] == 4
    assert profile["missing"]["total_cells"] == 1

    suggestions = suggest_targets(df)
    target_names = [s["column"] for s in suggestions]
    assert "target_class" in target_names or "target_reg" in target_names


def test_algorithms_catalog_and_hyperparameters():
    algorithms = list_algorithms()
    assert len(algorithms) >= 6
    alg_ids = [a.id for a in algorithms]
    assert "logistic_regression" in alg_ids
    assert "random_forest_classifier" in alg_ids
    assert "ridge_regression" in alg_ids

    spec = get_algorithm("random_forest_classifier", "classification")
    valid_params = validate_hyperparameters(spec, {"n_estimators": 50, "max_depth": 5})
    assert valid_params["n_estimators"] == 50
    assert valid_params["max_depth"] == 5

    # Out of bounds should raise ValidationError
    with pytest.raises(ValidationError):
        validate_hyperparameters(spec, {"n_estimators": 500000})


def test_train_classification_and_evaluation():
    np.random.seed(42)
    n = 100
    df = pd.DataFrame(
        {
            "feature_num": np.random.randn(n),
            "feature_cat": np.random.choice(["red", "blue", "green"], size=n),
            "churn": np.random.choice([0, 1], size=n),
        }
    )

    config = TrainingConfig(
        problem_type="classification",
        target_column="churn",
        feature_columns=["feature_num", "feature_cat"],
        test_size=0.25,
        random_seed=42,
        cv_folds=0,
    )

    spec = get_algorithm("logistic_regression", "classification")
    result = train_algorithm(df, spec, {}, config)
    assert result.pipeline is not None
    assert result.train_rows > 0
    assert "accuracy" in result.metrics
    assert "f1_weighted" in result.metrics
    assert result.metrics["accuracy"] >= 0.0
    assert result.reference_profile is not None
    assert "feature_num" in result.reference_profile["features"]
    assert "feature_cat" in result.reference_profile["features"]


def test_train_and_predict_with_missing_categorical_features():
    rng = np.random.default_rng(412)
    n = 180
    category = rng.choice(["basic", "pro", "enterprise"], size=n).astype(object)
    category[::9] = np.nan
    numeric = rng.normal(size=n)
    numeric[::13] = np.nan
    target = np.where(
        np.nan_to_num(numeric, nan=0) + np.where(category == "enterprise", 1.2, 0) > 0.15,
        "yes",
        "no",
    )
    df = pd.DataFrame({"usage_score": numeric, "plan": category, "renewed": target})
    config = TrainingConfig(
        problem_type="classification",
        target_column="renewed",
        feature_columns=["usage_score", "plan"],
        test_size=0.2,
        random_seed=42,
        cv_folds=3,
    )

    result = train_algorithm(
        df,
        get_algorithm("logistic_regression", "classification"),
        {},
        config,
    )

    assert result.metrics["accuracy"] > 0.65
    assert result.cv_metrics is not None
    predictions = result.pipeline.predict(df.loc[:8, ["usage_score", "plan"]])
    assert len(predictions) == 9


def test_train_regression():
    np.random.seed(42)
    n = 100
    x = np.random.randn(n)
    df = pd.DataFrame(
        {
            "x": x,
            "y": 2.5 * x + np.random.randn(n) * 0.1,
        }
    )

    config = TrainingConfig(
        problem_type="regression",
        target_column="y",
        feature_columns=["x"],
        test_size=0.2,
        random_seed=42,
        cv_folds=0,
    )

    spec = get_algorithm("ridge_regression", "regression")
    result = train_algorithm(df, spec, {}, config)
    assert result.pipeline is not None
    assert result.train_rows > 0
    assert "rmse" in result.metrics
    assert "r2" in result.metrics
    assert result.metrics["r2"] > 0.8


def test_drift_calculation():
    # PSI on equal bucket proportions vs shifted bucket proportions
    ref = [0.2, 0.2, 0.2, 0.2, 0.2]
    cur_same = [0.21, 0.19, 0.20, 0.20, 0.20]
    cur_shifted = [0.02, 0.03, 0.15, 0.35, 0.45]

    psi_same = population_stability_index(ref, cur_same)
    psi_shifted = population_stability_index(ref, cur_shifted)

    assert psi_same < 0.05, f"Expected small PSI for near-identical buckets, got {psi_same}"
    assert psi_shifted > 0.25, f"Expected large PSI for shifted buckets, got {psi_shifted}"


def test_csv_sniff_handles_a_split_utf8_character(tmp_path: Path) -> None:
    path = tmp_path / "unicode.csv"
    path.write_text(f"label,value\n{'a' * 4083}é,1\n", encoding="utf-8")
    assert read_dataframe(path, path.name).iloc[0]["label"].endswith("é")
