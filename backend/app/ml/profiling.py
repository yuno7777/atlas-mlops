from __future__ import annotations

from typing import Any

import pandas as pd
from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_any_dtype,
    is_numeric_dtype,
)

from app.ml.utils import json_safe


def classify_kind(series: pd.Series) -> str:
    if is_bool_dtype(series):
        return "boolean"
    if is_datetime64_any_dtype(series):
        return "datetime"
    if is_numeric_dtype(series):
        return "numeric"
    return "categorical"


def _numeric_stats(series: pd.Series) -> dict[str, Any]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return {
            "count": 0,
            "mean": None,
            "std": None,
            "min": None,
            "p25": None,
            "p50": None,
            "p75": None,
            "max": None,
            "zeros": 0,
            "negatives": 0,
            "outliers_iqr": 0,
            "skew": None,
        }
    q25, q50, q75 = values.quantile([0.25, 0.5, 0.75]).tolist()
    iqr = q75 - q25
    if iqr > 0:
        lower, upper = q25 - 1.5 * iqr, q75 + 1.5 * iqr
        outliers = int(((values < lower) | (values > upper)).sum())
    else:
        outliers = 0
    return {
        "count": int(values.size),
        "mean": float(values.mean()),
        "std": float(values.std()) if values.size > 1 else 0.0,
        "min": float(values.min()),
        "p25": float(q25),
        "p50": float(q50),
        "p75": float(q75),
        "max": float(values.max()),
        "zeros": int((values == 0).sum()),
        "negatives": int((values < 0).sum()),
        "outliers_iqr": outliers,
        "skew": float(values.skew()) if values.size > 2 else 0.0,
    }


def _categorical_stats(series: pd.Series, sample_size: int) -> dict[str, Any]:
    strings = series.dropna().astype(str).str.strip()
    strings = strings[strings != ""]
    total = int(strings.size)
    counts = strings.value_counts().head(10)
    return {
        "unique": int(strings.nunique()),
        "top": [
            {
                "value": str(value)[:120],
                "count": int(count),
                "percent": round(100 * count / total, 2) if total else 0.0,
            }
            for value, count in counts.items()
        ],
        "sampled": total < int(series.notna().sum()),
        "sample_size": sample_size,
    }


def profile_dataframe(df: pd.DataFrame, sample_rows: int = 50_000) -> dict[str, Any]:
    sample = df if len(df) <= sample_rows else df.sample(n=sample_rows, random_state=42)
    missing_columns = []
    for column in df.columns:
        count = int(df[column].isna().sum())
        if count:
            missing_columns.append(
                {"column": str(column), "count": count, "percent": round(100 * count / len(df), 2)}
            )
    duplicate_rows = int(df.duplicated().sum())
    numeric: list[dict[str, Any]] = []
    categorical: list[dict[str, Any]] = []
    datetime_columns: list[dict[str, Any]] = []
    constant_columns: list[str] = []
    high_missing: list[str] = []

    for column in sample.columns:
        series = sample[column]
        kind = classify_kind(series)
        if series.nunique(dropna=True) <= 1:
            constant_columns.append(str(column))
        missing_percent = 100 * float(df[column].isna().mean())
        if missing_percent > 50:
            high_missing.append(str(column))
        if kind == "numeric":
            numeric.append({"column": str(column), **_numeric_stats(series)})
        elif kind == "datetime":
            non_null = series.dropna()
            datetime_columns.append(
                {
                    "column": str(column),
                    "min": json_safe(non_null.min()) if not non_null.empty else None,
                    "max": json_safe(non_null.max()) if not non_null.empty else None,
                }
            )
        else:
            categorical.append({"column": str(column), **_categorical_stats(series, len(sample))})

    return {
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "memory_bytes": int(df.memory_usage(deep=True).sum()),
        "sampled": len(df) > sample_rows,
        "sample_size": int(len(sample)),
        "missing": {
            "total_cells": int(df.isna().sum().sum()),
            "percent": round(
                100 * float(df.isna().sum().sum()) / (len(df) * max(len(df.columns), 1)), 2
            ),
            "columns": missing_columns,
        },
        "duplicates": {
            "rows": duplicate_rows,
            "percent": round(100 * duplicate_rows / len(df), 2),
        },
        "numeric": numeric,
        "categorical": categorical,
        "datetime": datetime_columns,
        "constant_columns": constant_columns,
        "high_missing_columns": high_missing,
    }


def _is_id_like(name: str, unique_count: int, rows: int) -> bool:
    lowered = name.lower()
    if lowered.endswith("_id") or lowered in {"id", "uuid", "guid"}:
        return True
    return rows > 0 and unique_count / rows > 0.95 and unique_count > 20


def suggest_targets(df: pd.DataFrame, sample_rows: int = 5_000) -> list[dict[str, Any]]:
    sample = df if len(df) <= sample_rows else df.sample(n=sample_rows, random_state=42)
    rows = len(sample)
    suggestions: list[dict[str, Any]] = []
    hints = (
        "churn",
        "target",
        "label",
        "class",
        "outcome",
        "fraud",
        "price",
        "sale",
        "score",
        "default",
    )
    for column in sample.columns:
        series = sample[column]
        unique = int(series.nunique(dropna=True))
        if unique < 2:
            continue
        kind = classify_kind(series)
        if _is_id_like(str(column), unique, rows):
            continue
        name_hint = any(hint in str(column).lower() for hint in hints)
        if kind in {"categorical", "boolean"}:
            if 2 <= unique <= 20:
                task = "classification"
                if unique == 2:
                    reason = "Binary categorical column — suitable for classification"
                else:
                    reason = f"{unique} distinct values — suitable for multi-class classification"
                suggestions.append(
                    {
                        "column": str(column),
                        "task": task,
                        "reason": reason,
                        "score": 90 if name_hint else 60,
                    }
                )
        elif kind == "numeric":
            if 2 <= unique <= 10:
                suggestions.append(
                    {
                        "column": str(column),
                        "task": "classification",
                        "reason": f"Low-cardinality numeric column ({unique} values) — suitable for classification",
                        "score": 70 if name_hint else 40,
                    }
                )
            elif unique > 10:
                suggestions.append(
                    {
                        "column": str(column),
                        "task": "regression",
                        "reason": "Continuous numeric column — suitable for regression",
                        "score": 80 if name_hint else 35,
                    }
                )
    suggestions.sort(key=lambda item: item["score"], reverse=True)
    return suggestions[:4]


def validate_dataset(df: pd.DataFrame, profile: dict[str, Any], size_bytes: int) -> dict[str, Any]:
    checks: list[dict[str, str]] = []

    def add(name: str, passed: bool, message: str, warning_only: bool = False) -> None:
        status = "passed" if passed else ("warning" if warning_only else "failed")
        checks.append({"name": name, "status": status, "message": message})

    add("row_count", len(df) > 0, f"{len(df):,} rows")
    add("column_count", len(df.columns) > 0, f"{len(df.columns)} columns")
    add("file_size", size_bytes > 0, f"{size_bytes / 1024:.1f} KB")
    duplicate_percent = profile["duplicates"]["percent"]
    add(
        "duplicate_rows",
        duplicate_percent < 20,
        f"{duplicate_percent:.1f}% duplicate rows",
        warning_only=True,
    )
    high_missing = profile["high_missing_columns"]
    add(
        "missing_values",
        not high_missing,
        "No column exceeds 50% missing values"
        if not high_missing
        else f"{len(high_missing)} column(s) exceed 50% missing values",
        warning_only=True,
    )
    constant = profile["constant_columns"]
    add(
        "constant_columns",
        not constant,
        "No constant columns" if not constant else f"Constant columns: {', '.join(constant[:5])}",
        warning_only=True,
    )
    add("column_limit", len(df.columns) <= 500, f"{len(df.columns)} columns (limit 500)")
    passed = all(check["status"] != "failed" for check in checks)
    return {
        "passed": passed,
        "checks": checks,
        "target_suggestions": suggest_targets(df),
    }
