from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from app.core.config import settings


class AdminLoginRateLimitedError(Exception):
    pass


class AdminLoginGuard:
    """Bound failed administrator logins for the single-instance API deployment."""

    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        attempts = self._attempts[key]
        cutoff = now - settings.ADMIN_LOGIN_WINDOW_SECONDS
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if not attempts:
            self._attempts.pop(key, None)
            return deque()
        return attempts

    def check(self, key: str) -> None:
        now = monotonic()
        with self._lock:
            attempts = self._prune(key, now)
            if len(attempts) >= settings.ADMIN_LOGIN_MAX_FAILURES:
                raise AdminLoginRateLimitedError

    def record_failure(self, key: str) -> None:
        now = monotonic()
        with self._lock:
            self._prune(key, now)
            self._attempts[key].append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


admin_login_guard = AdminLoginGuard()
