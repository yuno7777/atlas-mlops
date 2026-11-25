from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        hide_input_in_errors=True,
    )

    app_name: str = "Atlas MLOps"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    version: str = "0.1.0"
    code_revision: str = "unknown"

    secret_key: str = "dev-only-insecure-secret-change-me-at-least-32-chars"  # noqa: S105
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(720, ge=1)
    allow_registration: bool = True

    database_url: str = "sqlite:///./data/atlas.db"
    database_pool_size: int = Field(5, ge=1)
    database_max_overflow: int = 10
    sql_echo: bool = False

    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    job_execution_mode: Literal["celery", "thread", "sync"] = "thread"
    thread_workers: int = Field(2, ge=1, le=32)
    redis_url: str = "redis://localhost:6379/0"
    stale_job_after_minutes: int = Field(180, ge=1)

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

    model_cache_size: int = Field(8, ge=1)
    model_cache_ttl_seconds: int = Field(300, ge=1)
    inference_threads: int = Field(4, ge=1, le=32)
    max_prediction_body_bytes: int = Field(default=2 * 1024 * 1024, ge=1024, le=64 * 1024 * 1024)
    inference_timeout_seconds: float = Field(10.0, gt=0, le=60)
    prediction_rate_limit_per_minute: int = Field(120, ge=1)
    login_rate_limit_per_minute: int = Field(10, ge=1)
    prediction_log_max_feature_bytes: int = 65_536

    enable_monitoring_scheduler: bool = False
    monitoring_interval_seconds: int = Field(900, ge=1)
    monitoring_window_hours: int = Field(24, ge=1)
    monitoring_min_samples: int = Field(30, ge=1)
    drift_psi_threshold: float = 0.2
    drift_share_threshold: float = 0.3
    performance_degradation_threshold: float = 0.15
    retrain_cooldown_hours: int = 12

    worker_metrics_port: int | None = Field(default=None, ge=1024, le=65535)
    log_level: str = "INFO"
    log_json: bool = True
    docs_enabled: bool = True

    trusted_proxy_headers: bool = False
    sentry_dsn: str | None = None

    otel_service_name: str = "atlas-api"
    otel_exporter_otlp_endpoint: str | None = None

    redis_connect_timeout_seconds: float = Field(2.0, gt=0, le=10)

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
        if self.environment == "production" and (self.debug or "*" in self.cors_origins_list):
            raise ValueError("Production requires debug disabled and explicit CORS origins")
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
        if (
            self.mlflow_enabled
            and not self.mlflow_tracking_uri.startswith(("http://", "https://"))
            and self.mlflow_artifact_root
            and not self.mlflow_artifact_root.startswith("s3://")
        ):
            Path(self.mlflow_artifact_root).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
