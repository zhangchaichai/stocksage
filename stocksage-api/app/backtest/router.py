"""Backtest API router."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtest import schemas, service
from app.db.models import User
from app.deps import get_current_user, get_db

router = APIRouter()


@router.post("/run", response_model=schemas.BacktestResultResponse)
async def run_backtest(
    body: schemas.BacktestRunRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await service.run_backtest(db, user.id, body.action_id, body.period_days)
    if result is None:
        raise HTTPException(
            status_code=400, detail="Backtest failed: no market data available"
        )
    await db.commit()
    return result


@router.post("/run-all", response_model=list[schemas.BacktestResultResponse])
async def run_all_pending(
    body: schemas.BacktestBatchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    results = await service.run_batch_backtest(db, user.id, body.period_days)
    await db.commit()
    return results


@router.get("/results", response_model=list[schemas.BacktestResultResponse])
async def list_results(
    symbol: str | None = Query(None),
    period: int | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items, total = await service.list_results(
        db, user.id, symbol, period, skip, limit
    )
    return items


@router.get("/results/{result_id}", response_model=schemas.BacktestResultResponse)
async def get_result(
    result_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await service.get_result(db, result_id)
    if result is None or result.user_id != user.id:
        raise HTTPException(status_code=404, detail="Backtest result not found")
    return result


@router.get("/stats", response_model=schemas.BacktestStatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.get_stats(db, user.id)


@router.get("/stats/{symbol}", response_model=schemas.BacktestStatsResponse)
async def get_symbol_stats(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.get_stats(db, user.id, symbol)


@router.get("/stats/wyckoff", response_model=schemas.WyckoffStatsResponse)
async def get_wyckoff_stats(
    symbol: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.get_wyckoff_stats(db, user.id, symbol)


@router.get("/stats/dealer", response_model=schemas.DealerSignalStatsResponse)
async def get_dealer_signal_stats(
    symbol: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.get_dealer_signal_stats(db, user.id, symbol)
