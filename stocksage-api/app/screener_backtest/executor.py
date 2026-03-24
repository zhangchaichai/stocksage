"""Screener backtest executor: batch validation of stock selection accuracy.

Given a completed screener job, fetches historical prices for the period after
the screening date and computes per-stock and aggregate performance metrics.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _compute_daily_returns(klines: list[dict]) -> list[float]:
    """Compute daily return series from klines."""
    closes = [float(k.get("收盘", 0)) for k in klines]
    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            returns.append((closes[i] - closes[i - 1]) / closes[i - 1])
    return returns


def _compute_sharpe(daily_returns: list[float], risk_free_annual: float = 0.02) -> float | None:
    """Compute annualised Sharpe ratio."""
    if len(daily_returns) < 5:
        return None
    mean_r = sum(daily_returns) / len(daily_returns)
    var = sum((r - mean_r) ** 2 for r in daily_returns) / len(daily_returns)
    std = math.sqrt(var)
    if std == 0:
        return None
    daily_rf = risk_free_annual / 252
    return round((mean_r - daily_rf) / std * math.sqrt(252), 4)


def execute_screener_backtest_sync(
    matches: list[dict[str, Any]],
    period_days: int,
    job_created_at: str | None = None,
) -> dict[str, Any]:
    """Execute a screener backtest synchronously.

    Args:
        matches: List of screener result dicts with {symbol, name, indicators}.
        period_days: Holding period in trading days.
        job_created_at: ISO date string of when the screener job was created
                        (used as the entry date baseline).

    Returns:
        Dict with aggregate stats and per-stock details.
    """
    try:
        from stocksage.data.fetcher import DataFetcher
        fetcher = DataFetcher()
    except Exception as e:
        logger.warning("DataFetcher not available: %s", e)
        return {"error": str(e), "stock_details": []}

    # Determine entry date from job_created_at
    entry_date_str = None
    if job_created_at:
        try:
            entry_date_str = str(job_created_at)[:10]
        except Exception:
            pass

    stock_details: list[dict[str, Any]] = []
    returns: list[float] = []
    all_daily_returns: list[float] = []

    for match in matches:
        symbol = match.get("symbol", "")
        name = match.get("name", "")
        indicators = match.get("indicators", {})

        # Entry price from indicators at screening time
        entry_price = indicators.get("close") or indicators.get("收盘")
        if entry_price is not None:
            try:
                entry_price = float(entry_price)
            except (TypeError, ValueError):
                entry_price = None

        # Fetch price data
        try:
            total_days = period_days + 30  # buffer
            price_data = fetcher.fetch_price_data(symbol, total_days)
            klines = price_data.get("klines", []) if price_data else []
        except Exception as e:
            logger.warning("Failed to fetch price data for %s: %s", symbol, e)
            stock_details.append({
                "symbol": symbol,
                "name": name,
                "entry_price": entry_price,
                "current_price": None,
                "price_change_pct": None,
                "max_gain_pct": None,
                "max_drawdown_pct": None,
                "error": str(e),
            })
            continue

        if not klines:
            stock_details.append({
                "symbol": symbol,
                "name": name,
                "entry_price": entry_price,
                "current_price": None,
                "price_change_pct": None,
                "max_gain_pct": None,
                "max_drawdown_pct": None,
                "error": "no_data",
            })
            continue

        # Filter klines after entry date
        if entry_date_str:
            after_entry = [k for k in klines if str(k.get("日期", ""))[:10] > entry_date_str]
        else:
            # Use all klines, take last period_days
            after_entry = klines

        period_klines = after_entry[:period_days] if after_entry else []

        if not period_klines:
            stock_details.append({
                "symbol": symbol,
                "name": name,
                "entry_price": entry_price,
                "current_price": None,
                "price_change_pct": None,
                "max_gain_pct": None,
                "max_drawdown_pct": None,
                "error": "no_data_in_period",
            })
            continue

        current_price = float(period_klines[-1].get("收盘", 0))

        # If entry_price not available from indicators, use the first kline
        if entry_price is None or entry_price <= 0:
            if entry_date_str:
                # Find the kline on or just before entry date
                pre_entry = [k for k in klines if str(k.get("日期", ""))[:10] <= entry_date_str]
                if pre_entry:
                    entry_price = float(pre_entry[-1].get("收盘", 0))
                else:
                    entry_price = float(period_klines[0].get("开盘", 0))
            else:
                entry_price = float(period_klines[0].get("开盘", 0))

        # Compute metrics
        if entry_price and entry_price > 0:
            price_change_pct = round((current_price - entry_price) / entry_price * 100, 2)
            highs = [float(k.get("最高", 0)) for k in period_klines]
            lows = [float(k.get("最低", 0)) for k in period_klines]
            max_gain_pct = round((max(highs) - entry_price) / entry_price * 100, 2) if highs else None
            max_drawdown_pct = round((min(lows) - entry_price) / entry_price * 100, 2) if lows else None

            returns.append(price_change_pct)

            daily_rets = _compute_daily_returns(period_klines)
            all_daily_returns.extend(daily_rets)
        else:
            price_change_pct = None
            max_gain_pct = None
            max_drawdown_pct = None

        stock_details.append({
            "symbol": symbol,
            "name": name,
            "entry_price": round(entry_price, 2) if entry_price else None,
            "current_price": round(current_price, 2),
            "price_change_pct": price_change_pct,
            "max_gain_pct": max_gain_pct,
            "max_drawdown_pct": max_drawdown_pct,
        })

    # Aggregate stats
    total_stocks = len(stock_details)
    avg_return_pct = round(sum(returns) / len(returns), 2) if returns else None
    win_rate = round(sum(1 for r in returns if r > 0) / len(returns) * 100, 2) if returns else None
    max_gain = round(max(returns), 2) if returns else None
    max_loss = round(min(returns), 2) if returns else None
    sharpe = _compute_sharpe(all_daily_returns)

    return {
        "total_stocks": total_stocks,
        "avg_return_pct": avg_return_pct,
        "win_rate": win_rate,
        "max_gain_pct": max_gain,
        "max_loss_pct": max_loss,
        "sharpe_ratio": sharpe,
        "stock_details": stock_details,
    }
