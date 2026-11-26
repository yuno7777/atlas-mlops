from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()
TRAINING_TASK_TIME_LIMIT_SECONDS = 2 * 3600
VISIBILITY_TIMEOUT_SECONDS = TRAINING_TASK_TIME_LIMIT_SECONDS + 300

celery_app = Celery(
    "atlas",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)
beat_schedule = {
    "reconcile-training-jobs": {
        "task": "app.workers.tasks.reconcile_training_jobs",
        "schedule": 120,
    }
}
if settings.enable_monitoring_scheduler:
    beat_schedule["scan-deployments-for-drift"] = {
        "task": "app.workers.tasks.scan_deployments_task",
        "schedule": settings.monitoring_interval_seconds,
    }

celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_time_limit=TRAINING_TASK_TIME_LIMIT_SECONDS,
    task_soft_time_limit=TRAINING_TASK_TIME_LIMIT_SECONDS - 60,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=settings.redis_connect_timeout_seconds,
    broker_transport_options={"visibility_timeout": VISIBILITY_TIMEOUT_SECONDS},
    result_backend_transport_options={"visibility_timeout": VISIBILITY_TIMEOUT_SECONDS},
    visibility_timeout=VISIBILITY_TIMEOUT_SECONDS,
    result_expires=3600,
    timezone="UTC",
    beat_schedule=beat_schedule,
)
