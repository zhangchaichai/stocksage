"""Usage service: record and query token usage."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import cast, func, select, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UsageRecord


async def record_usage(
    db: AsyncSession,
    user_id: uuid.UUID,
    run_id: uuid.UUID | None,
    tokens_input: int,
    tokens_output: int,
    provider: str = "deepseek",
) -> UsageRecord:
    """Insert a new UsageRecord."""
    record = UsageRecord(
        user_id=user_id,
        run_id=run_id,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        provider=provider,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


async def get_usage_summary(
    db: AsyncSession,
    user_id: uuid.UUID,
    period: str = "all",
) -> dict:
    """Aggregate tokens by period (all/week/month)."""
    q = select(
        func.coalesce(func.sum(UsageRecord.tokens_input), 0).label("total_input"),
        func.coalesce(func.sum(UsageRecord.tokens_output), 0).label("total_output"),
        func.count(UsageRecord.id).label("total_runs"),
    ).where(UsageRecord.user_id == user_id)

    now = datetime.now(timezone.utc)
    if period == "week":
        q = q.where(UsageRecord.created_at >= now - timedelta(days=7))
    elif period == "month":
        q = q.where(UsageRecord.created_at >= now - timedelta(days=30))

    result = await db.execute(q)
    row = result.one()
    total_input = int(row.total_input)
    total_output = int(row.total_output)

    return {
        "total_tokens_input": total_input,
        "total_tokens_output": total_output,
        "total_tokens": total_input + total_output,
        "total_runs": int(row.total_runs),
        "period": period,
    }


async def get_daily_usage(
    db: AsyncSession,
    user_id: uuid.UUID,
    days: int = 30,
) -> list[dict]:
    """Group usage by date for last N days."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    q = (
        select(
            cast(UsageRecord.created_at, Date).label("date"),
            func.coalesce(func.sum(UsageRecord.tokens_input), 0).label("tokens_input"),
            func.coalesce(func.sum(UsageRecord.tokens_output), 0).label("tokens_output"),
            func.count(UsageRecord.id).label("runs_count"),
        )
        .where(UsageRecord.user_id == user_id, UsageRecord.created_at >= since)
        .group_by(cast(UsageRecord.created_at, Date))
        .order_by(cast(UsageRecord.created_at, Date))
    )

    result = await db.execute(q)
    rows = result.all()

    return [
        {
            "date": str(row.date),
            "tokens_input": int(row.tokens_input),
            "tokens_output": int(row.tokens_output),
            "runs_count": int(row.runs_count),
        }
        for row in rows
    ]


async def get_today_usage(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> int:
    """Sum tokens for today."""
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

    q = select(
        func.coalesce(
            func.sum(UsageRecord.tokens_input + UsageRecord.tokens_output), 0
        ).label("total"),
    ).where(
        UsageRecord.user_id == user_id,
        UsageRecord.created_at >= start_of_day,
    )

    result = await db.execute(q)
    return int(result.scalar() or 0)
