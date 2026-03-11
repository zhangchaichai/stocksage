"""Run Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class RunCreate(BaseModel):
    workflow_id: uuid.UUID
    symbol: str = Field(min_length=1, max_length=16)
    stock_name: str = ""
    config_overrides: dict[str, Any] = {}


class BatchRunCreate(BaseModel):
    """Request body for bulk-submitting runs from screener results."""
    workflow_id: uuid.UUID
    symbols: list[str] = Field(min_length=1, max_length=50)
    stock_names: Optional[dict[str, str]] = None   # symbol → name map (optional)
    source: Optional[str] = None                   # e.g. "screener_job:{job_id}"
    config_overrides: dict[str, Any] = {}


class RunResponse(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    workflow_id: uuid.UUID | None
    symbol: str
    stock_name: str
    status: str
    config_overrides: dict[str, Any] | None
    result: dict[str, Any] | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RunListResponse(BaseModel):
    items: list[RunResponse]
    total: int
