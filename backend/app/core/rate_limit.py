from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from app.core.exceptions import RateLimitedError


class InMemoryRateLimiter:
    """Sliding-window limiter.

    Process-local by design for a single-node deployment. Documented limitation:
    multiple API replicas each enforce their own limit.
    """

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()

    def check(self, key: str, limit: int, window_seconds: int = 60) -> None:
        if limit <= 0:
            return
        now = time.monotonic()
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] <= now - window_seconds:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(window_seconds - (now - bucket[0])))
                raise RateLimitedError(
                    f"Rate limit exceeded. Retry in {retry_after} seconds.",
                    details={"retry_after": retry_after},
                )
            bucket.append(now)
            self._maybe_cleanup(now, window_seconds)

    def _maybe_cleanup(self, now: float, window_seconds: int) -> None:
        if now - self._last_cleanup < 60:
            return
        self._last_cleanup = now
        stale = [
            key
            for key, bucket in self._events.items()
            if not bucket or bucket[-1] <= now - window_seconds
        ]
        for key in stale:
            self._events.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


rate_limiter = InMemoryRateLimiter()
