"""Screener backtest service: run and manage screener-level backtests."""
from __future__ import annotations

import asyncio
import functools
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ScreenerBacktestResult, ScreenerJob

logger = logging.getLogger(__name__)

_screener_bt_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="screener-bt")


async def run_screener_backtest(
    db: AsyncSession,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    period_days: int = 30,
) -> ScreenerBacktestResult | None:
    """Run a screener backtest for a completed screener job.

    Returns the result, or None if the job is invalid or has no results.
    """
    # Check for existing backtest with same job + period
    existing = await db.execute(
        select(ScreenerBacktestResult)
        .where(ScreenerBacktestResult.job_id == job_id)
        .where(ScreenerBacktestResult.period_days == period_days)
    )
    found = existing.scalar_one_or_none()
    if found:
        return found

    # Load screener job
    job_result = await db.execute(
        select(ScreenerJob).where(ScreenerJob.id == job_id)
    )
    job = job_result.scalar_one_or_none()
    if job is None or job.status != "completed" or not job.results:
        return None

    matches = job.results  # list of {symbol, name, indicators, ...}
    strategy_id = job.strategy_id
    job_created_at = job.created_at.isoformat() if job.created_at else None

    # Run executor in thread pool (DataFetcher is sync)
    from app.screener_backtest.executor import execute_screener_backtest_sync

    loop = asyncio.get_event_loop()
    result_data = await loop.run_in_executor(
        _screener_bt_pool,
        functools.partial(
            execute_screener_backtest_sync, matches, period_days, job_created_at,
        ),
    )

    if result_data.get("error"):
        logger.warning("Screener backtest failed for job %s: %s", job_id, result_data["error"])
        return None

    # Create the result record
    from datetime import datetime, timezone
    bt = ScreenerBacktestResult(
        user_id=user_id,
        job_id=job_id,
        strategy_id=strategy_id,
        period_days=period_days,
        backtest_date=datetime.now(timezone.utc),
        total_stocks=result_data.get("total_stocks", 0),
        avg_return_pct=result_data.get("avg_return_pct"),
        win_rate=result_data.get("win_rate"),
        max_gain_pct=result_data.get("max_gain_pct"),
        max_loss_pct=result_data.get("max_loss_pct"),
        sharpe_ratio=result_data.get("sharpe_ratio"),
        stock_details=result_data.get("stock_details"),
    )
    db.add(bt)
    await db.flush()
    await db.refresh(bt)

    # Chain: Diagnosis → Memory → Evolution
    await _post_screener_backtest_chain(db, bt, user_id, result_data, strategy_id)

    return bt


async def list_screener_backtest_results(
    db: AsyncSession,
    user_id: uuid.UUID,
    strategy_id: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[ScreenerBacktestResult], int]:
    """List screener backtest results."""
    base = select(ScreenerBacktestResult).where(
        ScreenerBacktestResult.user_id == user_id
    )
    if strategy_id:
        base = base.where(ScreenerBacktestResult.strategy_id == strategy_id)

    count_q = select(sa_func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = base.order_by(ScreenerBacktestResult.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all()), total


async def get_screener_backtest_result(
    db: AsyncSession,
    result_id: uuid.UUID,
) -> ScreenerBacktestResult | None:
    result = await db.execute(
        select(ScreenerBacktestResult).where(ScreenerBacktestResult.id == result_id)
    )
    return result.scalar_one_or_none()


async def get_screener_backtest_stats(
    db: AsyncSession,
    user_id: uuid.UUID,
    strategy_id: str | None = None,
) -> dict[str, Any]:
    """Aggregate stats across screener backtests."""
    base = select(ScreenerBacktestResult).where(
        ScreenerBacktestResult.user_id == user_id
    )
    if strategy_id:
        base = base.where(ScreenerBacktestResult.strategy_id == strategy_id)

    result = await db.execute(base)
    results = list(result.scalars().all())

    if not results:
        return {
            "total_backtests": 0,
            "avg_return": 0.0,
            "avg_win_rate": 0.0,
            "avg_sharpe": 0.0,
            "best_strategy": None,
        }

    total = len(results)
    avg_return = sum(r.avg_return_pct or 0 for r in results) / total
    avg_win = sum(r.win_rate or 0 for r in results) / total
    sharpe_vals = [r.sharpe_ratio for r in results if r.sharpe_ratio is not None]
    avg_sharpe = sum(sharpe_vals) / len(sharpe_vals) if sharpe_vals else 0.0

    # Best strategy by avg return
    by_strategy: dict[str, list[float]] = {}
    for r in results:
        sid = r.strategy_id or "custom"
        if sid not in by_strategy:
            by_strategy[sid] = []
        by_strategy[sid].append(r.avg_return_pct or 0)

    best_strategy = None
    best_return = float("-inf")
    for sid, rets in by_strategy.items():
        avg = sum(rets) / len(rets)
        if avg > best_return:
            best_return = avg
            best_strategy = sid

    return {
        "total_backtests": total,
        "avg_return": round(avg_return, 2),
        "avg_win_rate": round(avg_win, 2),
        "avg_sharpe": round(avg_sharpe, 4),
        "best_strategy": best_strategy,
    }


# ── Post-backtest chain: Diagnosis → Memory → Evolution ──────────────────────

_diagnosis_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scr-bt-diag")


async def _post_screener_backtest_chain(
    db: AsyncSession,
    bt: ScreenerBacktestResult,
    user_id: uuid.UUID,
    result_data: dict[str, Any],
    strategy_id: str | None,
) -> None:
    """Run LLM diagnosis on screener selection quality, extract memory."""

    # Step 1: LLM Diagnosis
    try:
        from app.screener_backtest.diagnoser import generate_screener_diagnosis_sync
        from stocksage.llm.factory import create_llm

        llm = create_llm()
        loop = asyncio.get_event_loop()
        diagnosis = await loop.run_in_executor(
            _diagnosis_pool,
            functools.partial(
                generate_screener_diagnosis_sync,
                result_data,
                strategy_id,
                llm,
            ),
        )

        if diagnosis and not diagnosis.get("error"):
            bt.diagnosis = diagnosis
            await db.flush()
            logger.info("Screener backtest diagnosis generated for job %s", bt.job_id)
        else:
            logger.warning("Screener diagnosis error for job %s: %s", bt.job_id, diagnosis)
    except Exception as e:
        logger.warning("Screener diagnosis failed for job %s: %s", bt.job_id, e)

    # Step 2: Memory extraction — store as strategy_review
    try:
        from app.memory.extractor import extract_strategy_review

        mem_data = {
            "symbol": f"screener/{strategy_id or 'custom'}",
            "direction_correct": (bt.avg_return_pct or 0) > 0,
            "price_change_pct": bt.avg_return_pct,
            "period_days": bt.period_days,
            "diagnosis": bt.diagnosis,
            "win_rate": bt.win_rate,
            "total_stocks": bt.total_stocks,
        }
        await extract_strategy_review(
            db, user_id, f"screener/{strategy_id or 'custom'}", mem_data
        )
        logger.info("Screener backtest memory stored for strategy %s", strategy_id)
    except Exception as e:
        logger.warning("Screener backtest memory extraction failed: %s", e)
