"""Pydantic schemas for the scheduler module."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator


class ScheduledTaskCreate(BaseModel):
    """Request body to create a scheduled task."""
    name: str
    task_type: str  # screener / workflow_run / workflow_backtest / screener_backtest
    cron_expr: str  # e.g. "0 9 * * 1-5" (weekdays 9am)
    timezone: str = "Asia/Shanghai"
    enabled: bool = True
    config: dict[str, Any] = {}

    @field_validator("task_type")
    @classmethod
    def validate_task_type(cls, v: str) -> str:
        allowed = {
            "screener", "workflow_run", "workflow_backtest",
            "screener_backtest", "memory_forgetting",
        }
        if v not in allowed:
            raise ValueError(f"task_type must be one of {allowed}")
        return v

    @field_validator("cron_expr")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        parts = v.strip().split()
        if len(parts) not in (5, 6):
            raise ValueError(
                "cron_expr must have 5 or 6 fields: "
                "minute hour day month weekday [second]"
            )
        return v.strip()


class ScheduledTaskUpdate(BaseModel):
    """Request body to update a scheduled task."""
    name: Optional[str] = None
    cron_expr: Optional[str] = None
    timezone: Optional[str] = None
    enabled: Optional[bool] = None
    config: Optional[dict[str, Any]] = None

    @field_validator("cron_expr")
    @classmethod
    def validate_cron(cls, v: str | None) -> str | None:
        if v is None:
            return v
        parts = v.strip().split()
        if len(parts) not in (5, 6):
            raise ValueError("cron_expr must have 5 or 6 fields")
        return v.strip()


class ScheduledTaskResponse(BaseModel):
    """Response for a scheduled task."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    task_type: str
    cron_expr: str
    timezone: str
    enabled: bool
    config: dict[str, Any]
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[str] = None
    last_run_error: Optional[str] = None
    run_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None
