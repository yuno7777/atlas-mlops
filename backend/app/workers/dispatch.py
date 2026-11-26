from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.models.enums import JobStatus
from app.models.training import TrainingDispatch, TrainingJob, TrainingJobLog
from app.workers.executor import get_job_executor

logger = logging.getLogger(__name__)

DISPATCH_LEASE = timedelta(minutes=2)
FAILED_PUBLISH_DELAY = timedelta(seconds=30)
UNCLAIMED_DELIVERY_DELAY = timedelta(minutes=15)
DISPATCH_BATCH_SIZE = 100


def dispatch_training_job(job_id: str) -> bool:
    now = datetime.now(UTC)
    reserved_until = now + DISPATCH_LEASE
    queued = (
        select(TrainingJob.id)
        .where(TrainingJob.id == job_id, TrainingJob.status == JobStatus.QUEUED)
        .exists()
    )
    # Claim and commit before contacting the broker. A crash leaves a due time
    # instead of a held transaction, and another dispatcher can retry after it.
    with SessionLocal.begin() as db:
        attempt = db.scalar(
            update(TrainingDispatch)
            .where(TrainingDispatch.job_id == job_id, TrainingDispatch.available_at <= now, queued)
            .values(available_at=reserved_until, attempts=TrainingDispatch.attempts + 1)
            .returning(TrainingDispatch.attempts)
        )
    if attempt is None:
        return False

    try:
        get_job_executor().enqueue(job_id)
    except Exception:
        logger.exception(
            "Training dispatch failed; will retry", extra={"job_id": job_id, "attempt": attempt}
        )
        delivered = False
        delay = FAILED_PUBLISH_DELAY
    else:
        delivered = True
        delay = UNCLAIMED_DELIVERY_DELAY

    # A worker claim may have removed this row, or a newer dispatch may own it.
    with SessionLocal.begin() as db:
        updated = db.execute(
            update(TrainingDispatch)
            .where(
                TrainingDispatch.job_id == job_id,
                TrainingDispatch.attempts == attempt,
                TrainingDispatch.available_at == reserved_until,
            )
            .values(available_at=datetime.now(UTC) + delay)
        )
        if updated.rowcount == 1 and not delivered and attempt == 1:
            db.add(
                TrainingJobLog(
                    job_id=job_id,
                    level="warning",
                    message="Queue unavailable; awaiting dispatch recovery.",
                )
            )
    return delivered


def dispatch_due_training_jobs() -> int:
    with SessionLocal() as db:
        due = list(
            db.scalars(
                select(TrainingDispatch.job_id)
                .where(TrainingDispatch.available_at <= datetime.now(UTC))
                .order_by(TrainingDispatch.available_at, TrainingDispatch.job_id)
                .limit(DISPATCH_BATCH_SIZE)
            )
        )
    return sum(dispatch_training_job(job_id) for job_id in due)
