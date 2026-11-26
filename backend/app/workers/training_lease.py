from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.repositories.training import TrainingRepository
from app.schemas.training import TrainingExecutionPolicy

logger = logging.getLogger(__name__)


class LeaseLost(RuntimeError):
    """The worker can no longer write results for this job."""


class FitCancelled(RuntimeError):
    """The job owner asked for its fit process to stop."""


class TrainingLease:
    def __init__(self, job_id: str, duration_seconds: int) -> None:
        self.job_id = job_id
        self.token = str(uuid4())
        self.duration = timedelta(seconds=duration_seconds)
        self._stop = Event()
        self._thread = Thread(target=self._heartbeat, name="atlas-training-heartbeat", daemon=True)

    def claim(self, db: Session) -> bool:
        now = datetime.now(UTC)
        repository = TrainingRepository(db)
        job = repository.get_job(self.job_id)
        if job is None:
            return False
        policy = TrainingExecutionPolicy.model_validate(job.config.get("execution_policy", {}))
        claimed = repository.claim_job(
            self.job_id,
            now,
            self.token,
            now + self.duration,
            now + timedelta(seconds=policy.timeout_seconds),
        )
        db.commit()
        if claimed:
            self._thread.start()
        return claimed

    def guard(self, db: Session) -> None:
        """Hold the job's write lock and extend the lease in the caller's transaction."""
        now = datetime.now(UTC)
        if not TrainingRepository(db).update_lease(self.job_id, self.token, now + self.duration):
            raise LeaseLost(self.job_id)

    def check_fitting(self) -> None:
        with SessionLocal() as db:
            requested = TrainingRepository(db).fit_cancellation_requested(self.job_id, self.token)
        if requested is None:
            raise LeaseLost(self.job_id)
        if requested:
            raise FitCancelled(self.job_id)

    def commit(self, db: Session) -> None:
        self.guard(db)
        db.commit()

    def close(self) -> None:
        self._stop.set()
        if self._thread.ident is not None:
            self._thread.join()

    def _heartbeat(self) -> None:
        while not self._stop.wait(self.duration.total_seconds() / 4):
            try:
                with SessionLocal.begin() as db:
                    self.guard(db)
            except LeaseLost:
                return
            except SQLAlchemyError:
                logger.warning(
                    "Training heartbeat could not reach the database", extra={"job_id": self.job_id}
                )
