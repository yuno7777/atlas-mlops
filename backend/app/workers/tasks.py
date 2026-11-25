from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta

from celery.signals import setup_logging, worker_process_shutdown, worker_ready
from prometheus_client import CollectorRegistry, multiprocess, start_http_server
from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@setup_logging.connect
def _init_worker(**_kwargs) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)


@worker_ready.connect
def _start_metrics(**_kwargs) -> None:
    port = get_settings().worker_metrics_port
    if port is None:
        return
    if not os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        logger.error("Worker metrics require PROMETHEUS_MULTIPROC_DIR before Celery starts.")
        return
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    start_http_server(port, addr="0.0.0.0", registry=registry)  # noqa: S104
    logger.info("Worker metrics endpoint started", extra={"port": port})


@worker_process_shutdown.connect
def _release_gauges(pid: int, **_kwargs) -> None:
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        multiprocess.mark_process_dead(pid)


@celery_app.task(name="app.workers.tasks.run_training_job_task")
def run_training_job_task(job_id: str) -> None:
    from app.services.training_runner import execute_training_job

    try:
        execute_training_job(job_id)
    except Exception:
        logger.exception("Celery training task failed", extra={"job_id": job_id})
        raise


@celery_app.task(name="app.workers.tasks.scan_deployments_task")
def scan_deployments_task() -> int:
    from app.services.monitoring import scan_active_deployments

    return scan_active_deployments()


@celery_app.task(name="app.workers.tasks.reconcile_training_jobs")
def reconcile_training_jobs() -> None:
    from app.db.session import SessionLocal
    from app.models.enums import JobStatus
    from app.models.training import TrainingJob
    from app.services.training_runner import recover_stale_jobs

    recovered = recover_stale_jobs()
    cutoff = datetime.now(UTC) - timedelta(minutes=2)
    with SessionLocal() as db:
        undelivered = list(
            db.scalars(
                select(TrainingJob.id)
                .where(TrainingJob.status == JobStatus.QUEUED, TrainingJob.created_at < cutoff)
                .order_by(TrainingJob.created_at, TrainingJob.id)
                .limit(100)
            )
        )
    for job_id in undelivered:
        run_training_job_task.delay(job_id)
    if undelivered or recovered:
        logger.info(
            "Training queue reconciled", extra={"dispatched": len(undelivered), "stale": recovered}
        )
