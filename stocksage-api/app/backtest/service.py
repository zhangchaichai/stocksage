"""Backtest service: CRUD + stats aggregation."""
from __future__ import annotations

import asyncio
import functools
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BacktestResult, InvestmentAction

_backtest_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="backtest")


async def run_backtest(
    db: AsyncSession,
    user_id: uuid.UUID,
    action_id: uuid.UUID,
    period_days: int = 30,
) -> BacktestResult | None:
    """Run a single backtest for an investment action."""
    # Check if already backtested with same period
    existing = await db.execute(
        select(BacktestResult)
        .where(BacktestResult.action_id == action_id)
        .where(BacktestResult.period_days == period_days)
    )
    found = existing.scalar_one_or_none()
    if found:
        return found

    # Load action
    action_result = await db.execute(
        select(InvestmentAction).where(InvestmentAction.id == action_id)
    )
    action = action_result.scalar_one_or_none()
    if action is None:
        return None

    # Run backtest in thread pool (DataFetcher is sync)
    from app.backtest.executor import execute_backtest_sync

    loop = asyncio.get_event_loop()
    result_data = await loop.run_in_executor(
        _backtest_pool,
        functools.partial(execute_backtest_sync, action, period_days, user_id),
    )

    if result_data is None:
        return None

    bt = BacktestResult(**result_data)
    db.add(bt)
    await db.flush()
    await db.refresh(bt)
    return bt


async def run_batch_backtest(
    db: AsyncSession,
    user_id: uuid.UUID,
    period_days: int = 30,
) -> list[BacktestResult]:
    """Run backtests for all eligible actions that haven't been tested yet."""
    # Find actions without backtest for this period
    subq = select(BacktestResult.action_id).where(
        BacktestResult.period_days == period_days
    )
    actions_q = (
        select(InvestmentAction)
        .where(InvestmentAction.user_id == user_id)
        .where(InvestmentAction.action_type.in_(["buy", "sell"]))
        .where(InvestmentAction.id.notin_(subq))
    )
    result = await db.execute(actions_q)
    actions = list(result.scalars().all())

    results = []
    for action in actions:
        bt = await run_backtest(db, user_id, action.id, period_days)
        if bt:
            results.append(bt)
    return results


async def list_results(
    db: AsyncSession,
    user_id: uuid.UUID,
    symbol: str | None = None,
    period_days: int | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[BacktestResult], int]:
    """List backtest results with optional filters."""
    base = select(BacktestResult).where(BacktestResult.user_id == user_id)
    if symbol:
        base = base.where(BacktestResult.symbol == symbol)
    if period_days:
        base = base.where(BacktestResult.period_days == period_days)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = base.order_by(BacktestResult.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all()), total


async def get_result(
    db: AsyncSession,
    result_id: uuid.UUID,
) -> BacktestResult | None:
    result = await db.execute(
        select(BacktestResult).where(BacktestResult.id == result_id)
    )
    return result.scalar_one_or_none()


async def get_stats(
    db: AsyncSession,
    user_id: uuid.UUID,
    symbol: str | None = None,
) -> dict[str, Any]:
    """Calculate aggregate backtest statistics."""
    base = select(BacktestResult).where(BacktestResult.user_id == user_id)
    if symbol:
        base = base.where(BacktestResult.symbol == symbol)

    result = await db.execute(base)
    results = list(result.scalars().all())

    if not results:
        return {
            "total_actions": 0,
            "direction_accuracy": 0.0,
            "avg_return": 0.0,
            "win_rate": 0.0,
            "max_drawdown": 0.0,
            "dimension_accuracy": {},
            "avg_sharpe": 0.0,
            "avg_sortino": 0.0,
            "avg_var_95": 0.0,
            "wyckoff_accuracy": {},
            "dealer_signal_accuracy": 0.0,
        }

    total = len(results)
    correct = sum(1 for r in results if r.direction_correct)
    wins = sum(1 for r in results if r.price_change_pct and r.price_change_pct > 0)
    avg_return = sum(r.price_change_pct or 0 for r in results) / total
    max_dd = min((r.max_drawdown_pct or 0) for r in results)

    # Dimension accuracy from diagnosis
    dim_counts: dict[str, list[float]] = {}
    for r in results:
        if r.diagnosis and isinstance(r.diagnosis, dict):
            for sug in r.diagnosis.get("improvement_suggestions", []):
                if isinstance(sug, dict):
                    dim = sug.get("target", sug.get("type", "unknown"))
                    if dim not in dim_counts:
                        dim_counts[dim] = []
                    dim_counts[dim].append(1.0 if r.direction_correct else 0.0)

    dimension_accuracy = {
        k: round(sum(v) / len(v) * 100, 1) if v else 0
        for k, v in dim_counts.items()
    }

    # Phase 4: enhanced risk stats
    sharpe_vals = [r.sharpe_ratio for r in results if r.sharpe_ratio is not None]
    sortino_vals = [r.sortino_ratio for r in results if r.sortino_ratio is not None]
    var_vals = [r.var_95 for r in results if r.var_95 is not None]

    avg_sharpe = round(sum(sharpe_vals) / len(sharpe_vals), 4) if sharpe_vals else 0.0
    avg_sortino = round(sum(sortino_vals) / len(sortino_vals), 4) if sortino_vals else 0.0
    avg_var_95 = round(sum(var_vals) / len(var_vals), 4) if var_vals else 0.0

    # Wyckoff phase accuracy
    wyckoff_buckets: dict[str, list[float]] = {}
    for r in results:
        phase = r.wyckoff_phase_at_action
        if phase:
            if phase not in wyckoff_buckets:
                wyckoff_buckets[phase] = []
            wyckoff_buckets[phase].append(1.0 if r.direction_correct else 0.0)

    wyckoff_accuracy = {
        k: round(sum(v) / len(v) * 100, 1)
        for k, v in wyckoff_buckets.items()
        if v
    }

    # Dealer signal accuracy: accuracy when dealer signals were present
    dealer_results = [r for r in results if r.dealer_signals_at_action]
    dealer_signal_accuracy = 0.0
    if dealer_results:
        dealer_correct = sum(1 for r in dealer_results if r.direction_correct)
        dealer_signal_accuracy = round(dealer_correct / len(dealer_results) * 100, 1)

    return {
        "total_actions": total,
        "direction_accuracy": round(correct / total * 100, 1),
        "avg_return": round(avg_return, 2),
        "win_rate": round(wins / total * 100, 1),
        "max_drawdown": round(max_dd, 2),
        "dimension_accuracy": dimension_accuracy,
        "avg_sharpe": avg_sharpe,
        "avg_sortino": avg_sortino,
        "avg_var_95": avg_var_95,
        "wyckoff_accuracy": wyckoff_accuracy,
        "dealer_signal_accuracy": dealer_signal_accuracy,
    }


async def get_wyckoff_stats(
    db: AsyncSession,
    user_id: uuid.UUID,
    symbol: str | None = None,
) -> dict[str, Any]:
    """Calculate Wyckoff phase accuracy stats."""
    base = select(BacktestResult).where(BacktestResult.user_id == user_id)
    if symbol:
        base = base.where(BacktestResult.symbol == symbol)

    result = await db.execute(base)
    results = list(result.scalars().all())

    phase_counts: dict[str, int] = {}
    phase_correct: dict[str, list[float]] = {}
    for r in results:
        phase = r.wyckoff_phase_at_action
        if phase:
            phase_counts[phase] = phase_counts.get(phase, 0) + 1
            if phase not in phase_correct:
                phase_correct[phase] = []
            phase_correct[phase].append(1.0 if r.direction_correct else 0.0)

    wyckoff_accuracy = {
        k: round(sum(v) / len(v) * 100, 1)
        for k, v in phase_correct.items()
        if v
    }

    total_with_wyckoff = sum(phase_counts.values())

    return {
        "wyckoff_accuracy": wyckoff_accuracy,
        "phase_counts": phase_counts,
        "total_with_wyckoff": total_with_wyckoff,
    }


async def get_dealer_signal_stats(
    db: AsyncSession,
    user_id: uuid.UUID,
    symbol: str | None = None,
) -> dict[str, Any]:
    """Calculate dealer signal accuracy stats."""
    base = select(BacktestResult).where(BacktestResult.user_id == user_id)
    if symbol:
        base = base.where(BacktestResult.symbol == symbol)

    result = await db.execute(base)
    results = list(result.scalars().all())

    dealer_results = [r for r in results if r.dealer_signals_at_action]
    total_with_signals = len(dealer_results)
    dealer_signal_accuracy = 0.0
    signal_type_counts: dict[str, int] = {}

    if dealer_results:
        dealer_correct = sum(1 for r in dealer_results if r.direction_correct)
        dealer_signal_accuracy = round(dealer_correct / len(dealer_results) * 100, 1)

        for r in dealer_results:
            signals = r.dealer_signals_at_action or []
            for s in signals:
                if isinstance(s, dict):
                    sig_type = s.get("type", "unknown")
                    signal_type_counts[sig_type] = signal_type_counts.get(sig_type, 0) + 1

    return {
        "dealer_signal_accuracy": dealer_signal_accuracy,
        "total_with_signals": total_with_signals,
        "signal_type_counts": signal_type_counts,
    }
