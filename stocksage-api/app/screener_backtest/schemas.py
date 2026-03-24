"""Pydantic schemas for screener backtest module."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class ScreenerBacktestRunRequest(BaseModel):
    """Request body to run a screener backtest."""
    job_id: uuid.UUID
    period_days: int = 30


class ScreenerBacktestStockDetail(BaseModel):
    """Per-stock backtest result."""
    symbol: str
    name: str = ""
    entry_price: Optional[float] = None
    current_price: Optional[float] = None
    price_change_pct: Optional[float] = None
    max_gain_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    error: Optional[str] = None


class ScreenerBacktestResultResponse(BaseModel):
    """Response for a screener backtest result."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    job_id: uuid.UUID
    strategy_id: Optional[str] = None
    period_days: int
    backtest_date: Optional[datetime] = None
    total_stocks: int = 0
    avg_return_pct: Optional[float] = None
    win_rate: Optional[float] = None
    max_gain_pct: Optional[float] = None
    max_loss_pct: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    stock_details: Optional[list[dict[str, Any]]] = None
    diagnosis: Optional[dict[str, Any]] = None
    created_at: datetime


class ScreenerBacktestStatsResponse(BaseModel):
    """Aggregate screener backtest statistics."""
    total_backtests: int = 0
    avg_return: float = 0.0
    avg_win_rate: float = 0.0
    avg_sharpe: float = 0.0
    best_strategy: Optional[str] = None
