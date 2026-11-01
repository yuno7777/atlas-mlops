from __future__ import annotations

import logging

from celery.signals import worker_process_init

from app.core.logging import configure_logging
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@worker_process_init.connect
def _init_worker(**_kwargs) -> None:
    configure_logging()
    logger.info("Atlas training worker process initialized")


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
