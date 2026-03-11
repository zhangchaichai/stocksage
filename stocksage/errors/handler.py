"""错误处理：超时包装器 + 熔断器。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitBreaker:
    """熔断器：连续失败超阈值后快速拒绝，一段时间后半开尝试恢复。

    状态: CLOSED → OPEN → HALF_OPEN → CLOSED
    """

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 30.0):
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._state = "CLOSED"

    @property
    def state(self) -> str:
        if self._state == "OPEN":
            if time.time() - self._last_failure_time > self._recovery_timeout:
                self._state = "HALF_OPEN"
        return self._state

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = "CLOSED"

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self._failure_threshold:
            self._state = "OPEN"
            logger.warning("熔断器打开: 连续 %d 次失败", self._failure_count)

    def allow_request(self) -> bool:
        return self.state != "OPEN"


def with_retry(max_retries: int = 2, delay: float = 1.0) -> Callable:
    """重试装饰器。"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            "%s 第 %d 次失败，%0.1fs 后重试: %s",
                            func.__name__, attempt + 1, delay, e,
                        )
                        time.sleep(delay)
            raise last_exception  # type: ignore[misc]
        return wrapper
    return decorator
