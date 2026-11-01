from __future__ import annotations

import contextlib
import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from functools import lru_cache

from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError

logger = logging.getLogger(__name__)


class JobExecutor:
    """Dispatches training work according to the configured execution mode."""

    def __init__(self, mode: str, workers: int) -> None:
        self.mode = mode
        self.workers = workers
        self._pool: ThreadPoolExecutor | None = None
        self._futures: set[Future] = set()
        self._lock = threading.Lock()

    @property
    def pool(self) -> ThreadPoolExecutor:
        if self._pool is None:
            self._pool = ThreadPoolExecutor(
                max_workers=max(1, self.workers), thread_name_prefix="atlas-training"
            )
        return self._pool

    def enqueue(self, job_id: str) -> None:
        if self.mode == "sync":
            self._run(job_id)
            return
        if self.mode == "thread":
            future = self.pool.submit(self._run, job_id)
            with self._lock:
                self._futures.add(future)
            future.add_done_callback(self._discard)
            return
        if self.mode == "celery":
            try:
                from app.workers.tasks import run_training_job_task

                run_training_job_task.delay(job_id)
            except Exception as exc:
                logger.exception("Could not enqueue Celery task")
                raise ServiceUnavailableError(
                    "The background worker queue is unavailable.", details={"reason": str(exc)}
                ) from exc
            return
        raise ServiceUnavailableError(f"Unknown execution mode '{self.mode}'.")

    def _discard(self, future: Future) -> None:
        with self._lock:
            self._futures.discard(future)

    def _run(self, job_id: str) -> None:
        from app.services.training_runner import execute_training_job

        try:
            execute_training_job(job_id)
        except Exception:
            logger.exception("Background training execution failed", extra={"job_id": job_id})

    def shutdown(self, wait: bool = False) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=wait, cancel_futures=False)


@lru_cache
def get_job_executor() -> JobExecutor:
    settings = get_settings()
    return JobExecutor(settings.job_execution_mode, settings.thread_workers)


def reset_job_executor() -> None:
    with contextlib.suppress(Exception):
        get_job_executor().shutdown(wait=False)
    get_job_executor.cache_clear()
