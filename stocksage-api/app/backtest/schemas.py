from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BacktestRunRequest(BaseModel):
    action_id: uuid.UUID
    period_days: int = 30


class BacktestBatchRequest(BaseModel):
    period_days: int = 30


class BacktestDiagnosisResponse(BaseModel):
    accuracy_verdict: str | None = None
    score: float | None = None
    direction_correct: bool | None = None
    magnitude_error: str | None = None
    correct_insights: list[str] = []
    missed_factors: list[str] = []
    root_cause: str | None = None
    improvement_suggestions: list[dict] = []


class BacktestResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    action_id: uuid.UUID
    run_id: uuid.UUID | None = None
    symbol: str
    period_days: int
    backtest_date: datetime | None = None
    action_price: float | None = None
    current_price: float | None = None
    price_change_pct: float | None = None
    max_drawdown_pct: float | None = None
    max_gain_pct: float | None = None
    predicted_direction: str | None = None
    actual_direction: str | None = None
    direction_correct: bool | None = None
    diagnosis: dict | None = None
    # Phase 4: enhanced fields
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    var_95: float | None = None
    wyckoff_phase_at_action: str | None = None
    dealer_signals_at_action: list[dict] | None = None
    created_at: datetime


class BacktestStatsResponse(BaseModel):
    total_actions: int = 0
    direction_accuracy: float = 0.0
    avg_return: float = 0.0
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    dimension_accuracy: dict[str, float] = {}
    # Phase 4: enhanced stats
    avg_sharpe: float = 0.0
    avg_sortino: float = 0.0
    avg_var_95: float = 0.0
    wyckoff_accuracy: dict[str, float] = {}
    dealer_signal_accuracy: float = 0.0


class WyckoffStatsResponse(BaseModel):
    wyckoff_accuracy: dict[str, float] = {}
    phase_counts: dict[str, int] = {}
    total_with_wyckoff: int = 0


class DealerSignalStatsResponse(BaseModel):
    dealer_signal_accuracy: float = 0.0
    total_with_signals: int = 0
    signal_type_counts: dict[str, int] = {}
