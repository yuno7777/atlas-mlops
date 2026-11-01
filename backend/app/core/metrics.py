from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "atlas_http_requests_total",
    "HTTP requests processed.",
    ["method", "route", "status"],
)
HTTP_LATENCY = Histogram(
    "atlas_http_request_duration_seconds",
    "HTTP request latency.",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
TRAINING_JOBS = Counter(
    "atlas_training_jobs_total",
    "Training job terminal states.",
    ["status"],
)
EXPERIMENTS = Counter(
    "atlas_experiments_total",
    "Experiment terminal states.",
    ["status", "algorithm"],
)
PREDICTIONS = Counter(
    "atlas_predictions_total",
    "Predictions by deployment and status.",
    ["deployment_id", "status"],
)
PREDICTION_LATENCY = Histogram(
    "atlas_prediction_latency_seconds",
    "Prediction latency.",
    ["deployment_id"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
DRIFT_DETECTIONS = Counter(
    "atlas_drift_detections_total",
    "Monitoring results by status.",
    ["deployment_id", "status"],
)
ACTIVE_TRAINING_JOBS = Gauge(
    "atlas_active_training_jobs",
    "Training jobs currently running in this process.",
)
