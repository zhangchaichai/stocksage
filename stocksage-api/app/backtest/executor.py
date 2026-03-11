"""Backtest executor: compute actual returns vs predicted direction."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

from app.db.models import InvestmentAction

logger = logging.getLogger(__name__)

# Map recommendation to direction
_RECOMMENDATION_TO_DIRECTION = {
    "strong_buy": "up",
    "buy": "up",
    "overweight": "up",
    "hold": "neutral",
    "neutral": "neutral",
    "sell": "down",
    "underweight": "down",
    "strong_sell": "down",
}


def _get_predicted_direction(action: InvestmentAction) -> str:
    """Infer predicted direction from action's analysis_snapshot."""
    snapshot = action.analysis_snapshot or {}
    recommendation = snapshot.get("recommendation", "").lower().replace(" ", "_")
    return _RECOMMENDATION_TO_DIRECTION.get(recommendation, "neutral")


def _get_actual_direction(price_change_pct: float) -> str:
    """Determine actual direction from price change."""
    if price_change_pct > 2.0:
        return "up"
    elif price_change_pct < -2.0:
        return "down"
    return "neutral"


def _compute_daily_returns(klines: list[dict]) -> list[float]:
    """Compute daily return series from klines."""
    closes = [float(k.get("\u6536\u76d8", 0)) for k in klines]
    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            returns.append((closes[i] - closes[i - 1]) / closes[i - 1])
    return returns


def _compute_sharpe(daily_returns: list[float], risk_free_annual: float = 0.02) -> float | None:
    """Compute annualised Sharpe ratio (252 trading days)."""
    if len(daily_returns) < 5:
        return None
    mean_r = sum(daily_returns) / len(daily_returns)
    var = sum((r - mean_r) ** 2 for r in daily_returns) / len(daily_returns)
    std = math.sqrt(var)
    if std == 0:
        return None
    daily_rf = risk_free_annual / 252
    return round((mean_r - daily_rf) / std * math.sqrt(252), 4)


def _compute_sortino(daily_returns: list[float], risk_free_annual: float = 0.02) -> float | None:
    """Compute annualised Sortino ratio (downside deviation only)."""
    if len(daily_returns) < 5:
        return None
    daily_rf = risk_free_annual / 252
    mean_r = sum(daily_returns) / len(daily_returns)
    downside = [min(r - daily_rf, 0) ** 2 for r in daily_returns]
    downside_var = sum(downside) / len(downside)
    downside_std = math.sqrt(downside_var)
    if downside_std == 0:
        return None
    return round((mean_r - daily_rf) / downside_std * math.sqrt(252), 4)


def _compute_var95(daily_returns: list[float]) -> float | None:
    """Compute historical VaR at 95% confidence (percentage)."""
    if len(daily_returns) < 10:
        return None
    sorted_r = sorted(daily_returns)
    idx = max(0, int(len(sorted_r) * 0.05) - 1)
    return round(sorted_r[idx] * 100, 4)


def _get_wyckoff_phase(action: InvestmentAction) -> str | None:
    """Extract Wyckoff phase from analysis snapshot at the time of action."""
    snapshot = action.analysis_snapshot or {}

    # Try decision → dealer_behavior_assessment → wyckoff_phase
    decision = snapshot.get("decision", {})
    if isinstance(decision, dict):
        dba = decision.get("dealer_behavior_assessment", {})
        if isinstance(dba, dict) and dba.get("wyckoff_phase"):
            return dba["wyckoff_phase"]

    # Try analysis → dealer_behavior_analyst
    analysis = snapshot.get("analysis", {})
    if isinstance(analysis, dict):
        dealer = analysis.get("dealer_behavior_analyst", {})
        if isinstance(dealer, dict):
            verdict = dealer.get("dealer_verdict", {})
            if isinstance(verdict, dict) and verdict.get("wyckoff_phase"):
                return verdict["wyckoff_phase"]

    # Try data → indicators → dealer
    data = snapshot.get("data", {})
    if isinstance(data, dict):
        indicators = data.get("indicators", {})
        if isinstance(indicators, dict):
            dealer_ind = indicators.get("dealer", {})
            if isinstance(dealer_ind, dict) and dealer_ind.get("wyckoff_phase"):
                return dealer_ind["wyckoff_phase"]

    return None


def _get_dealer_signals(action: InvestmentAction) -> list[dict] | None:
    """Extract dealer distribution signals from analysis snapshot."""
    snapshot = action.analysis_snapshot or {}

    # Try data → indicators → dealer → dist_signals
    data = snapshot.get("data", {})
    if isinstance(data, dict):
        indicators = data.get("indicators", {})
        if isinstance(indicators, dict):
            dealer_ind = indicators.get("dealer", {})
            if isinstance(dealer_ind, dict):
                signals = dealer_ind.get("dist_signals", [])
                if signals:
                    return [
                        {
                            "type": s.get("type", "unknown"),
                            "confidence": s.get("confidence", 0),
                            "description": s.get("description", ""),
                        }
                        for s in signals
                        if isinstance(s, dict)
                    ]

    # Try analysis → dealer_behavior_analyst → distribution_signals
    analysis = snapshot.get("analysis", {})
    if isinstance(analysis, dict):
        dealer = analysis.get("dealer_behavior_analyst", {})
        if isinstance(dealer, dict):
            dist = dealer.get("distribution_signals", {})
            if isinstance(dist, dict):
                sigs = dist.get("signals", [])
                if sigs:
                    return [
                        {
                            "type": s.get("type", "unknown"),
                            "confidence": s.get("confidence", 0),
                            "description": s.get("description", ""),
                        }
                        for s in sigs
                        if isinstance(s, dict)
                    ]

    return None


def execute_backtest_sync(
    action: InvestmentAction,
    period_days: int,
    user_id,
) -> dict[str, Any] | None:
    """Execute a backtest for an investment action (synchronous, uses DataFetcher).

    Returns a dict of BacktestResult fields (without id/created_at) or None if data
    unavailable.
    """
    try:
        from stocksage.data.fetcher import DataFetcher

        fetcher = DataFetcher()
    except Exception as e:
        logger.warning("DataFetcher not available: %s", e)
        return None

    # Fetch price data for the period after the action date
    total_days = period_days + 30  # extra buffer
    price_data = fetcher.fetch_price_data(action.symbol, total_days)

    if not price_data or not price_data.get("klines"):
        logger.warning("No price data for %s", action.symbol)
        return None

    klines = price_data["klines"]

    # Find the action date and the backtest end date
    action_date = action.action_date
    if hasattr(action_date, "date"):
        action_date_str = action_date.strftime("%Y-%m-%d")
    else:
        action_date_str = str(action_date)[:10]

    # Find klines after action_date within period_days
    after_action = []
    for k in klines:
        kline_date = str(k.get("\u65e5\u671f", ""))[:10]
        if kline_date > action_date_str:
            after_action.append(k)

    if not after_action:
        logger.warning(
            "No price data after action date %s for %s",
            action_date_str,
            action.symbol,
        )
        return None

    # Get prices in period
    period_klines = after_action[:period_days]  # approximate trading days
    if not period_klines:
        return None

    action_price = action.price
    current_price = float(period_klines[-1].get("\u6536\u76d8", 0))

    # Calculate metrics
    highs = [float(k.get("\u6700\u9ad8", 0)) for k in period_klines]
    lows = [float(k.get("\u6700\u4f4e", 0)) for k in period_klines]

    price_change_pct = (
        ((current_price - action_price) / action_price * 100)
        if action_price > 0
        else 0
    )
    max_high = max(highs) if highs else current_price
    min_low = min(lows) if lows else current_price
    max_gain_pct = (
        ((max_high - action_price) / action_price * 100) if action_price > 0 else 0
    )
    max_drawdown_pct = (
        ((min_low - action_price) / action_price * 100) if action_price > 0 else 0
    )

    predicted_direction = _get_predicted_direction(action)
    actual_direction = _get_actual_direction(price_change_pct)
    direction_correct = (predicted_direction == actual_direction) or (
        predicted_direction in ("up", "neutral")
        and actual_direction in ("up", "neutral")
        and price_change_pct > 0
    )

    # Risk metrics (Phase 4)
    daily_returns = _compute_daily_returns(period_klines)
    sharpe = _compute_sharpe(daily_returns)
    sortino = _compute_sortino(daily_returns)
    var_95 = _compute_var95(daily_returns)

    # Wyckoff & dealer signals at action time
    wyckoff_phase = _get_wyckoff_phase(action)
    dealer_signals = _get_dealer_signals(action)

    backtest_date_val = period_klines[-1].get("\u65e5\u671f", "")
    try:
        backtest_date = datetime.strptime(str(backtest_date_val)[:10], "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    except (ValueError, TypeError):
        backtest_date = datetime.now(timezone.utc)

    return {
        "user_id": user_id,
        "action_id": action.id,
        "run_id": action.run_id,
        "symbol": action.symbol,
        "period_days": period_days,
        "backtest_date": backtest_date,
        "action_price": round(action_price, 2),
        "current_price": round(current_price, 2),
        "price_change_pct": round(price_change_pct, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "max_gain_pct": round(max_gain_pct, 2),
        "predicted_direction": predicted_direction,
        "actual_direction": actual_direction,
        "direction_correct": direction_correct,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "var_95": var_95,
        "wyckoff_phase_at_action": wyckoff_phase,
        "dealer_signals_at_action": dealer_signals,
    }
