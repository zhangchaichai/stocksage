"""Screener backtest API router."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.deps import get_current_user, get_db
from app.screener_backtest import schemas, service

router = APIRouter()


@router.post("/run", response_model=schemas.ScreenerBacktestResultResponse)
async def run_screener_backtest(
    body: schemas.ScreenerBacktestRunRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Run a backtest for a completed screener job."""
    result = await service.run_screener_backtest(
        db, user.id, body.job_id, body.period_days,
    )
    if result is None:
        raise HTTPException(
            status_code=400,
            detail="Screener backtest failed: job not found, not completed, or no market data",
        )
    await db.commit()
    return result


@router.get("/results", response_model=list[schemas.ScreenerBacktestResultResponse])
async def list_results(
    strategy_id: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List screener backtest results."""
    items, _ = await service.list_screener_backtest_results(
        db, user.id, strategy_id, skip, limit,
    )
    return items


@router.get("/results/{result_id}", response_model=schemas.ScreenerBacktestResultResponse)
async def get_result(
    result_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a specific screener backtest result."""
    result = await service.get_screener_backtest_result(db, result_id)
    if result is None or result.user_id != user.id:
        raise HTTPException(status_code=404, detail="Screener backtest result not found")
    return result


@router.get("/stats", response_model=schemas.ScreenerBacktestStatsResponse)
async def get_stats(
    strategy_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get aggregate screener backtest statistics."""
    return await service.get_screener_backtest_stats(db, user.id, strategy_id)
