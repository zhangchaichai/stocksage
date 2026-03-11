"""TTLCache tests."""

from __future__ import annotations

import time

from stocksage.data.cache import TTLCache


class TestTTLCache:
    def test_set_and_get(self):
        cache = TTLCache(default_ttl=60)
        cache.set("k1", "v1")
        assert cache.get("k1") == "v1"

    def test_get_missing_key(self):
        cache = TTLCache()
        assert cache.get("nonexistent") is None

    def test_expired_entry(self):
        cache = TTLCache(default_ttl=1)
        # ttl=0 falls back to default_ttl due to `ttl or default_ttl`,
        # so we manually insert an already-expired entry.
        cache._store["k1"] = ("v1", time.time() - 1)
        assert cache.get("k1") is None

    def test_custom_ttl(self):
        cache = TTLCache(default_ttl=0)
        cache.set("k1", "v1", ttl=60)
        assert cache.get("k1") == "v1"

    def test_clear(self):
        cache = TTLCache()
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        cache.clear()
        assert cache.get("k1") is None
        assert cache.get("k2") is None

    def test_overwrite(self):
        cache = TTLCache()
        cache.set("k1", "v1")
        cache.set("k1", "v2")
        assert cache.get("k1") == "v2"
