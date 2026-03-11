"""Indicator dashboard API router."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.models import User
from app.deps import get_current_user
from app.indicators.schemas import IndicatorGroup, IndicatorResponse

logger = logging.getLogger(__name__)
router = APIRouter()

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="indicators")

# ─── 内存缓存：symbol+period → (result, expire_ts) ───────────────────────────
_CACHE_TTL = 40 * 60  # 40 分钟


@dataclass
class _CacheEntry:
    result: dict[str, Any]
    expire_at: float


_cache: dict[tuple[str, int], _CacheEntry] = {}


def _cache_get(symbol: str, period: int) -> dict[str, Any] | None:
    entry = _cache.get((symbol, period))
    if entry and time.monotonic() < entry.expire_at:
        return entry.result
    _cache.pop((symbol, period), None)
    return None


def _cache_set(symbol: str, period: int, result: dict[str, Any]) -> None:
    _cache[(symbol, period)] = _CacheEntry(
        result=result,
        expire_at=time.monotonic() + _CACHE_TTL,
    )

# Category labels for EN / ZH (ZH label used as fallback display)
_CATEGORY_META: dict[str, tuple[str, str]] = {
    "technical": ("Technical", "技术指标"),
    "kbar": ("K-Bar Patterns", "K线形态"),
    "rolling": ("Rolling Statistics", "滚动统计"),
    "ashare": ("A-Share Factors", "A股特色因子"),
    "risk": ("Risk Metrics", "风险指标"),
    "fundamental": ("Fundamentals", "基本面"),
    "fund_flow": ("Fund Flow", "资金流向"),
    "margin": ("Margin Trading", "融资融券"),
    "dealer": ("Dealer / Wyckoff", "庄家行为 / Wyckoff"),
}


def _compute_indicators_sync(symbol: str, days: int) -> dict[str, Any]:
    """Fetch data and compute all indicators synchronously."""
    from stocksage.data.fetcher import DataFetcher
    from stocksage.data.indicators import compute_all_indicators

    fetcher = DataFetcher()

    # Gather raw data needed by compute_all_indicators
    data: dict[str, Any] = {}
    data["price_data"] = fetcher.fetch_price_data(symbol, days=days)
    data["stock_info"] = fetcher.fetch_stock_info(symbol)
    data["financial"] = fetcher.fetch_financial(symbol)
    data["quarterly"] = fetcher.fetch_quarterly(symbol)
    data["fund_flow"] = fetcher.fetch_fund_flow(symbol)
    data["margin"] = fetcher.fetch_margin_data(symbol)

    try:
        data["balance_sheet"] = fetcher.fetch_balance_sheet(symbol)
    except Exception:
        data["balance_sheet"] = {}

    indicators = compute_all_indicators(data)
    return indicators


@router.get("/{symbol}", response_model=IndicatorResponse)
async def get_indicators(
    symbol: str,
    period: int = Query(120, ge=5, le=500, description="K-line period in days"),
    current_user: User = Depends(get_current_user),
):
    """Compute all indicators for a given stock symbol.

    Results are cached in-process for 40 minutes per (symbol, period) pair
    to avoid redundant computation on repeated requests.
    """
    import asyncio

    sym = symbol.upper()

    # ── 命中缓存直接返回 ──────────────────────────────────────────────────────
    cached = _cache_get(sym, period)
    if cached is not None:
        logger.debug("Indicator cache hit: %s period=%d", sym, period)
        raw = cached
    else:
        loop = asyncio.get_event_loop()
        try:
            raw = await loop.run_in_executor(
                _pool,
                partial(_compute_indicators_sync, sym, period),
            )
        except Exception as e:
            logger.exception("Indicator computation failed for %s: %s", sym, e)
            raise HTTPException(status_code=502, detail=f"Failed to compute indicators: {e}")
        _cache_set(sym, period, raw)
        logger.debug("Indicator cache miss (computed & cached): %s period=%d", sym, period)

    groups: list[IndicatorGroup] = []
    for key, (en_label, _zh_label) in _CATEGORY_META.items():
        data = raw.get(key)
        if data and isinstance(data, dict):
            groups.append(IndicatorGroup(name=key, label=en_label, indicators=data))

    # Include any extra top-level keys not in our meta map
    for key, value in raw.items():
        if key not in _CATEGORY_META and isinstance(value, dict) and value:
            groups.append(IndicatorGroup(name=key, label=key.replace("_", " ").title(), indicators=value))

    return IndicatorResponse(symbol=sym, period=period, groups=groups)
