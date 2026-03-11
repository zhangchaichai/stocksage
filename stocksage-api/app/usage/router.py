"""Usage router: summary, daily, quota."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import User
from app.db.session import get_db
from app.deps import get_current_user
from app.usage.schemas import DailyUsage, QuotaResponse, UsageSummary
from app.usage.service import get_daily_usage, get_today_usage, get_usage_summary

router = APIRouter()


@router.get("/summary", response_model=UsageSummary)
async def usage_summary(
    period: str = Query("all", pattern="^(all|week|month)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get usage summary for the authenticated user."""
    data = await get_usage_summary(db, current_user.id, period)
    return UsageSummary(**data)


@router.get("/daily", response_model=list[DailyUsage])
async def daily_usage(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get daily usage breakdown for the authenticated user."""
    rows = await get_daily_usage(db, current_user.id, days)
    return [DailyUsage(**row) for row in rows]


@router.get("/quota", response_model=QuotaResponse)
async def quota_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get quota status for the authenticated user."""
    used_today = await get_today_usage(db, current_user.id)
    daily_limit = settings.DAILY_TOKEN_QUOTA
    return QuotaResponse(
        daily_limit=daily_limit,
        used_today=used_today,
        remaining=max(0, daily_limit - used_today),
    )
