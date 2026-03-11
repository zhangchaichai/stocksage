from __future__ import annotations

from pydantic import BaseModel


class UsageSummary(BaseModel):
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    total_tokens: int = 0
    total_runs: int = 0
    period: str = "all"


class DailyUsage(BaseModel):
    date: str
    tokens_input: int = 0
    tokens_output: int = 0
    runs_count: int = 0


class UsageDashboardResponse(BaseModel):
    summary: UsageSummary
    daily: list[DailyUsage] = []


class QuotaResponse(BaseModel):
    daily_limit: int
    used_today: int
    remaining: int
