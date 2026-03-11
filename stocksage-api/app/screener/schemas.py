"""Pydantic schemas for the stock screener."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class ScreenerFilter(BaseModel):
    """A single filter condition."""
    field: str          # e.g. "pe", "rsi_14", "macd_cross"
    operator: str       # "lt", "gt", "eq", "lte", "gte", "ne"
    value: Any          # number or string


class ScreenerJobCreate(BaseModel):
    """Request body to create a screening job."""
    filters: list[ScreenerFilter] = []
    pool: str = "hs300"  # hs300, zz500, zz1000, all_a, custom, ...
    custom_symbols: Optional[list[str]] = None
    strategy_id: Optional[str] = None    # use a predefined strategy
    top_n: int = 20
    enable_ai_score: bool = False         # whether to run AIScorer after screener
    data_date: Optional[str] = None       # e.g. "2026-03-06", anchor pywencai to a specific trading day
    # ── time-period filtering ──────────────────────────────────────────────────
    date_from: Optional[str] = None       # e.g. "2026-01-01", start date for price/indicator data
    date_to: Optional[str] = None         # e.g. "2026-03-08", end date for price/indicator data
    # ── market / board filtering ──────────────────────────────────────────────
    # Valid values: "sh_main"(沪主板), "sz_main"(深主板), "cyb"(创业板),
    #               "kcb"(科创板), "bj"(北交所)
    # Empty list = no additional filter (use full pool)
    market_filters: list[str] = []


class ScreenerMatch(BaseModel):
    """A stock matching the screener criteria."""
    symbol: str
    name: str
    indicators: dict[str, Any]
    ai_score: Optional[float] = None
    ai_reason: Optional[str] = None


class ScreenerJobResponse(BaseModel):
    """Screener job status and results."""
    id: str
    status: str  # queued, running, completed, failed
    filters: list[ScreenerFilter]
    pool: str
    strategy_id: Optional[str] = None
    top_n: int = 20
    enable_ai_score: bool = False
    data_date: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    market_filters: list[str] = []
    total_scanned: int
    candidates: list[ScreenerMatch] = []       # Layer 1: full candidate list
    candidate_count: int = 0                    # total candidates (may differ from len(candidates))
    matches: list[ScreenerMatch] = []           # Layer 2: AI-scored top_n results
    analyst_reports: Optional[dict[str, Any]] = None  # AI analyst team reports
    error: Optional[str] = None
    created_at: str


# ── Strategy schemas ──────────────────────────────────────────────────────────

class StrategyListItem(BaseModel):
    """Summary item for the strategy list endpoint."""
    id: str
    name: str
    description: str
    icon: str
    category: str
    risk_level: str
    suitable_for: str
    pool: str
    sell_condition_count: int


class StrategyDetail(StrategyListItem):
    """Full strategy detail including queries, fields and risk params."""
    pywencai_queries: list[str]
    display_fields: list[dict[str, str]]
    sell_conditions: list[dict[str, Any]]
    risk_params: dict[str, Any]


# ── NL query schemas ──────────────────────────────────────────────────────────

class NLQueryRequest(BaseModel):
    """Natural language screener query."""
    query: str


class NLQueryResponse(BaseModel):
    """Result of NL → pywencai query translation."""
    pywencai_query: str
    strategy_hint: Optional[str] = None   # matched strategy id if any
    error: Optional[str] = None


# ── Strategy backtest schemas ─────────────────────────────────────────────────

class StrategyBacktestRequest(BaseModel):
    """Request body for strategy performance simulation."""
    strategy_id: str
    job_id: str               # completed screener job to backtest from
    period_days: int = 30     # holding period to simulate


class StrategyBacktestItem(BaseModel):
    """Per-stock simulated return."""
    symbol: str
    name: str
    entry_price: Optional[float] = None
    current_price: Optional[float] = None
    price_change_pct: Optional[float] = None


class StrategyBacktestResponse(BaseModel):
    """Aggregate strategy backtest stats."""
    strategy_id: str
    strategy_name: str
    job_id: str
    period_days: int
    total_stocks: int
    avg_return_pct: Optional[float] = None
    win_rate: Optional[float] = None
    max_gain_pct: Optional[float] = None
    max_loss_pct: Optional[float] = None
    items: list[StrategyBacktestItem] = []
