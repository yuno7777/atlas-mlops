from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from app.core.exceptions import DatasetValidationError

ALLOWED_EXTENSIONS: dict[str, str] = {
    ".csv": "text/csv",
    ".parquet": "application/vnd.apache.parquet",
    ".json": "application/json",
}
ALLOWED_CONTENT_TYPES: set[str] = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "application/octet-stream",
    "application/vnd.apache.parquet",
    "application/parquet",
    "application/json",
    "text/plain",
}
MAX_COLUMNS = 500


def normalize_extension(filename: str) -> tuple[str, str]:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        supported = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise DatasetValidationError(
            f"Unsupported file type '{suffix or 'unknown'}'. Use {supported}."
        )
    return suffix, ALLOWED_EXTENSIONS[suffix]


def validate_content_type(content_type: str | None) -> None:
    if not content_type:
        return
    base = content_type.split(";")[0].strip().lower()
    if base and base not in ALLOWED_CONTENT_TYPES:
        raise DatasetValidationError(f"Unsupported content type '{base}'.")


def sniff_file(path: Path, extension: str) -> None:
    head = path.open("rb").read(8)
    if not head:
        raise DatasetValidationError("Uploaded file is empty.")
    if extension == ".parquet" and not head.startswith(b"PAR1"):
        raise DatasetValidationError("File is not a valid Parquet file (missing magic bytes).")
    if extension == ".json":
        stripped = head.lstrip()
        if not stripped or stripped[:1] not in (b"{", b"["):
            raise DatasetValidationError("File is not valid JSON (expected an object or array).")
    if extension == ".csv":
        try:
            path.open("rb").read(4096).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DatasetValidationError(
                "CSV must be UTF-8 encoded. Re-export the file as UTF-8 and try again."
            ) from exc


def read_dataframe(path: Path, filename: str) -> pd.DataFrame:
    extension, _ = normalize_extension(filename)
    sniff_file(path, extension)
    try:
        if extension == ".csv":
            df = pd.read_csv(path, encoding="utf-8-sig")
        elif extension == ".parquet":
            df = pd.read_parquet(path)
        else:
            try:
                df = pd.read_json(path)
            except ValueError:
                df = pd.read_json(path, lines=True)
    except DatasetValidationError:
        raise
    except Exception as exc:
        message = str(exc).splitlines()[0][:280] or exc.__class__.__name__
        raise DatasetValidationError(f"Could not parse the file: {message}") from exc

    if not isinstance(df, pd.DataFrame):
        raise DatasetValidationError("The file did not produce a tabular dataset.")
    return sanitize_dataframe(df)


def sanitize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty and len(df.columns) == 0:
        raise DatasetValidationError("The dataset has no columns.")
    df = df.copy()
    columns: list[str] = []
    for index, column in enumerate(df.columns):
        name = str(column).strip()
        if not name or name.lower().startswith("unnamed:"):
            name = f"column_{index + 1}"
        columns.append(name)
    if len(set(columns)) != len(columns):
        duplicates = sorted({name for name in columns if columns.count(name) > 1})
        raise DatasetValidationError(f"Duplicate column names after normalization: {duplicates}")
    if len(columns) > MAX_COLUMNS:
        raise DatasetValidationError(f"Datasets may have at most {MAX_COLUMNS} columns.")
    df.columns = columns
    if df.shape[0] == 0:
        raise DatasetValidationError("The dataset has no rows.")
    return df


def schema_payload(df: pd.DataFrame, max_sample_values: int = 5) -> list[dict[str, Any]]:
    from app.ml.profiling import classify_kind

    sample = df.head(500)
    schema: list[dict[str, Any]] = []
    for column in df.columns:
        series = sample[column].dropna()
        unique = int(series.nunique()) if not series.empty else 0
        schema.append(
            {
                "name": str(column),
                "dtype": str(df[column].dtype),
                "kind": classify_kind(df[column]),
                "nullable": bool(df[column].isna().any()),
                "unique_count": unique,
                "sample_values": [
                    str(value)[:120] for value in series.unique()[:max_sample_values]
                ],
            }
        )
    return schema
