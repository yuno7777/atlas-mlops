from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "atlas",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_time_limit=3600 * 2,
    task_soft_time_limit=3600 * 2 - 60,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
    timezone="UTC",
    beat_schedule={
        "scan-deployments-for-drift": {
            "task": "app.workers.tasks.scan_deployments_task",
            "schedule": settings.monitoring_interval_seconds,
        }
    },
)
