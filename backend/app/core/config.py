from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Atlas MLOps"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    version: str = "0.1.0"

    secret_key: str = "dev-only-insecure-secret-change-me-at-least-32-chars"  # noqa: S105
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 720
    allow_registration: bool = True

    database_url: str = "sqlite:///./data/atlas.db"
    database_pool_size: int = 5
    database_max_overflow: int = 10
    sql_echo: bool = False

    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    job_execution_mode: Literal["celery", "thread", "sync"] = "thread"
    thread_workers: int = 2
    redis_url: str = "redis://localhost:6379/0"
    stale_job_after_minutes: int = 180

    mlflow_enabled: bool = True
    mlflow_tracking_uri: str = "sqlite:///./data/mlflow.db"
    mlflow_artifact_root: str = "./data/mlflow-artifacts"
    mlflow_experiment_prefix: str = "atlas"

    artifact_root: Path = Path("./data/artifacts")
    storage_backend: Literal["local", "s3"] = "local"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_use_ssl: bool = True

    max_upload_mb: int = 100
    max_profile_sample_rows: int = 50_000
    max_preview_rows: int = 100
    max_batch_records: int = 1_000

    model_cache_size: int = 8
    model_cache_ttl_seconds: int = 300
    inference_threads: int = 4
    prediction_rate_limit_per_minute: int = 120
    login_rate_limit_per_minute: int = 10
    prediction_log_max_feature_bytes: int = 65_536

    enable_monitoring_scheduler: bool = False
    monitoring_interval_seconds: int = 900
    monitoring_window_hours: int = 24
    monitoring_min_samples: int = 30
    drift_psi_threshold: float = 0.2
    drift_share_threshold: float = 0.3
    performance_degradation_threshold: float = 0.15
    retrain_cooldown_hours: int = 12

    log_level: str = "INFO"
    log_json: bool = True
    docs_enabled: bool = True

    trusted_proxy_headers: bool = False
    sentry_dsn: str | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @model_validator(mode="after")
    def _validate_production(self) -> Settings:
        if self.environment == "production" and "change-me" in self.secret_key:
            raise ValueError("SECRET_KEY must be set to a strong value in production")
        if len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        if self.storage_backend == "s3" and not self.s3_bucket:
            raise ValueError("S3_BUCKET is required when STORAGE_BACKEND=s3")
        if not 0 < self.max_upload_mb <= 2048:
            raise ValueError("MAX_UPLOAD_MB must be between 1 and 2048")
        return self

    def ensure_directories(self) -> None:
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        if self.is_sqlite:
            path = self.database_url.removeprefix("sqlite:///")
            if path and path != ":memory:":
                Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        if self.mlflow_tracking_uri.startswith("sqlite:///"):
            path = self.mlflow_tracking_uri.removeprefix("sqlite:///")
            if path:
                Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        if self.mlflow_artifact_root and not self.mlflow_artifact_root.startswith("s3://"):
            Path(self.mlflow_artifact_root).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
