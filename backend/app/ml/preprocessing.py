from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from pandas.api.types import is_bool_dtype, is_datetime64_any_dtype, is_numeric_dtype
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.core.exceptions import TrainingError


@dataclass
class PreparedFeatures:
    frame: pd.DataFrame
    numeric_columns: list[str]
    categorical_columns: list[str]
    schema: list[dict[str, Any]]
    dropped_columns: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _categorical_series(series: pd.Series) -> pd.Series:
    converted = series.astype("string").str.strip()
    return converted.mask(converted == "", pd.NA)


def prepare_training_features(features: pd.DataFrame) -> PreparedFeatures:
    if features.shape[1] == 0:
        raise TrainingError("No feature columns are available for training.")
    numeric_columns: list[str] = []
    categorical_columns: list[str] = []
    dropped: list[str] = []
    warnings: list[str] = []
    prepared = pd.DataFrame(index=features.index)

    for column in features.columns:
        series = features[column]
        non_null = series.notna().sum()
        if non_null == 0:
            dropped.append(str(column))
            continue
        if is_bool_dtype(series):
            prepared[str(column)] = series.map({True: "true", False: "false"}).astype("string")
            categorical_columns.append(str(column))
        elif is_numeric_dtype(series):
            prepared[str(column)] = pd.to_numeric(series, errors="coerce")
            numeric_columns.append(str(column))
        elif is_datetime64_any_dtype(series):
            formatted = series.dt.strftime("%Y-%m-%dT%H:%M:%S")
            prepared[str(column)] = formatted.astype("string")
            categorical_columns.append(str(column))
        else:
            prepared[str(column)] = _categorical_series(series)
            categorical_columns.append(str(column))

    if dropped:
        warnings.append(f"Dropped all-null feature columns: {', '.join(dropped)}")
    if not numeric_columns and not categorical_columns:
        raise TrainingError("No usable feature columns remain after cleaning.")

    schema = [
        {
            "name": column,
            "kind": "numeric" if column in numeric_columns else "categorical",
            "dtype": str(features[column].dtype),
        }
        for column in prepared.columns
    ]
    return PreparedFeatures(
        frame=prepared,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        schema=schema,
        dropped_columns=dropped,
        warnings=warnings,
    )


def coerce_frame_to_schema(frame: pd.DataFrame, schema: list[dict[str, Any]]) -> pd.DataFrame:
    """Coerce a raw feature frame into the dtypes the preprocessing pipeline was fit on."""
    output: dict[str, pd.Series] = {}
    for feature in schema:
        name = feature["name"]
        if name not in frame.columns:
            raise TrainingError(f"Missing feature column '{name}'.")
        series = frame[name]
        if feature["kind"] == "numeric":
            output[name] = pd.to_numeric(series, errors="coerce").astype(float)
        else:
            output[name] = _categorical_series(series)
    return pd.DataFrame(output, index=frame.index)


def build_preprocessor(prepared: PreparedFeatures) -> ColumnTransformer:
    transformers: list[tuple[str, Pipeline, list[str]]] = []
    if prepared.numeric_columns:
        transformers.append(
            (
                "numeric",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", StandardScaler()),
                    ]
                ),
                prepared.numeric_columns,
            )
        )
    if prepared.categorical_columns:
        transformers.append(
            (
                "categorical",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        (
                            "encoder",
                            OneHotEncoder(
                                handle_unknown="ignore",
                                sparse_output=False,
                                min_frequency=0.01,
                                max_categories=30,
                            ),
                        ),
                    ]
                ),
                prepared.categorical_columns,
            )
        )
    if not transformers:
        raise TrainingError("Unable to build preprocessing: no numeric or categorical features.")
    return ColumnTransformer(
        transformers=transformers,
        remainder="drop",
        verbose_feature_names_out=False,
    )
