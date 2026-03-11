"""Memory Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MemoryItemResponse(BaseModel):
    id: uuid.UUID
    memory_type: str
    content: str
    structured_data: dict[str, Any] | None
    importance_weight: float
    access_count: int
    happened_at: datetime | None
    is_archived: bool
    categories: list[str] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class MemoryCategoryResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    summary: str | None
    item_count: int = 0

    model_config = {"from_attributes": True}


class MemoryItemListResponse(BaseModel):
    items: list[MemoryItemResponse]
    total: int


class PreferenceCreate(BaseModel):
    key: str = Field(min_length=1)
    value: str = Field(min_length=1)
    category: str = "user/investment_style"


class StockMemoryResponse(BaseModel):
    symbol: str
    profile: MemoryItemResponse | None = None
    analysis_events: list[MemoryItemResponse] = []
    price_anchors: list[MemoryItemResponse] = []
    strategy_reviews: list[MemoryItemResponse] = []
    actions: list[MemoryItemResponse] = []


class TimelineEntry(BaseModel):
    date: str
    type: str
    content: str
    structured_data: dict[str, Any] | None = None
