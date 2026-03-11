"""TTL 缓存：简单的内存字典缓存，支持过期时间。"""

from __future__ import annotations

import time
from typing import Any


class TTLCache:
    """基于字典的 TTL 缓存。"""

    def __init__(self, default_ttl: int = 3600):
        self._store: dict[str, tuple[Any, float]] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        """获取缓存值，已过期返回 None。"""
        if key not in self._store:
            return None
        value, expire_at = self._store[key]
        if time.time() > expire_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """设置缓存值。"""
        expire_at = time.time() + (ttl or self._default_ttl)
        self._store[key] = (value, expire_at)

    def clear(self) -> None:
        """清空缓存。"""
        self._store.clear()
