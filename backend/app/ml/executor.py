from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from typing import TypeVar

from app.core.exceptions import ServiceUnavailableError

Result = TypeVar("Result")


class InferenceExecutor:
    """Give online scoring a fixed worker budget without an unbounded queue."""

    def __init__(self, workers: int, timeout_seconds: float) -> None:
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="atlas-inference")
        self._slots = threading.BoundedSemaphore(workers)
        self._timeout_seconds = timeout_seconds

    def run(self, operation: Callable[[], Result]) -> Result:
        if not self._slots.acquire(blocking=False):
            raise ServiceUnavailableError("All inference workers are busy.", code="inference_busy")
        try:
            future = self._pool.submit(copy_context().run, operation)
        except RuntimeError as exc:
            self._slots.release()
            raise ServiceUnavailableError("Inference is shutting down.") from exc
        future.add_done_callback(lambda _: self._slots.release())
        try:
            return future.result(timeout=self._timeout_seconds)
        except TimeoutError as exc:
            future.cancel()
            raise ServiceUnavailableError(
                "Inference exceeded its deadline.", code="inference_timeout", status_code=504
            ) from exc

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
