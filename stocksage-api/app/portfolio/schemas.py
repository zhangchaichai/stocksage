"""Portfolio Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ActionCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    stock_name: str = ""
    action_type: str = Field(min_length=1, max_length=16)  # buy / sell / hold / watch
    price: float = Field(gt=0)
    quantity: int | None = None
    amount: float | None = None
    reason: str | None = None
    run_id: uuid.UUID | None = None
    action_date: datetime


class ActionUpdate(BaseModel):
    price: float | None = None
    quantity: int | None = None
    amount: float | None = None
    reason: str | None = None
    action_type: str | None = None


class ActionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    run_id: uuid.UUID | None
    symbol: str
    stock_name: str
    action_type: str
    price: float
    quantity: int | None
    amount: float | None
    reason: str | None
    analysis_snapshot: dict[str, Any] | None
    action_date: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class ActionListResponse(BaseModel):
    items: list[ActionResponse]
    total: int


class PortfolioHolding(BaseModel):
    symbol: str
    stock_name: str
    quantity: int
    avg_cost: float
    last_analysis_date: str | None = None


class PortfolioSummary(BaseModel):
    total_cost: float
    holding_count: int
    holdings: list[PortfolioHolding]
