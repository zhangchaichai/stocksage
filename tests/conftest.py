"""Shared test fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_klines() -> list[dict]:
    """30-day sample K-line data for indicator tests."""
    base_price = 100.0
    klines = []
    for i in range(30):
        offset = (i % 7 - 3) * 0.5
        close = round(base_price + i * 0.2 + offset, 2)
        klines.append({
            "日期": f"2026-01-{i + 1:02d}",
            "开盘": round(close - 0.3, 2),
            "收盘": close,
            "最高": round(close + 0.5, 2),
            "最低": round(close - 0.5, 2),
            "成交量": 10000 + i * 100,
            "换手率": round(1.0 + i * 0.05, 2),
        })
    return klines
