"""Portfolio service: investment action CRUD + portfolio summary."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InvestmentAction, WorkflowRun


async def create_action(
    db: AsyncSession,
    user_id: uuid.UUID,
    symbol: str,
    stock_name: str,
    action_type: str,
    price: float,
    action_date,
    quantity: int | None = None,
    amount: float | None = None,
    reason: str | None = None,
    run_id: uuid.UUID | None = None,
) -> InvestmentAction:
    # Build analysis_snapshot from associated run if provided
    analysis_snapshot: dict[str, Any] | None = None
    if run_id:
        result = await db.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))
        run = result.scalar_one_or_none()
        if run and run.result:
            decision = run.result.get("decision", {})
            analysis_snapshot = {
                "recommendation": decision.get("recommendation"),
                "confidence": decision.get("confidence"),
                "target_price": decision.get("target_price"),
                "core_logic": decision.get("core_logic"),
            }

    action = InvestmentAction(
        user_id=user_id,
        run_id=run_id,
        symbol=symbol,
        stock_name=stock_name,
        action_type=action_type,
        price=price,
        quantity=quantity,
        amount=amount,
        reason=reason,
        analysis_snapshot=analysis_snapshot,
        action_date=action_date,
    )
    db.add(action)
    await db.flush()
    await db.refresh(action)
    return action


async def get_action(db: AsyncSession, action_id: uuid.UUID) -> InvestmentAction | None:
    result = await db.execute(select(InvestmentAction).where(InvestmentAction.id == action_id))
    return result.scalar_one_or_none()


async def list_actions(
    db: AsyncSession,
    user_id: uuid.UUID,
    symbol: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[InvestmentAction], int]:
    base = select(InvestmentAction).where(InvestmentAction.user_id == user_id)
    if symbol:
        base = base.where(InvestmentAction.symbol == symbol)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = base.order_by(InvestmentAction.action_date.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all()), total


async def update_action(
    db: AsyncSession, action: InvestmentAction, updates: dict[str, Any],
) -> InvestmentAction:
    for k, v in updates.items():
        if v is not None:
            setattr(action, k, v)
    await db.flush()
    await db.refresh(action)
    return action


async def delete_action(db: AsyncSession, action: InvestmentAction) -> None:
    await db.delete(action)
    await db.flush()


async def get_portfolio_summary(
    db: AsyncSession, user_id: uuid.UUID,
) -> dict[str, Any]:
    """Aggregate buy/sell actions to compute current holdings."""
    q = (
        select(InvestmentAction)
        .where(InvestmentAction.user_id == user_id)
        .where(InvestmentAction.action_type.in_(["buy", "sell"]))
        .order_by(InvestmentAction.action_date.asc())
    )
    result = await db.execute(q)
    actions = list(result.scalars().all())

    # Aggregate per symbol
    holdings: dict[str, dict] = {}
    for act in actions:
        if act.symbol not in holdings:
            holdings[act.symbol] = {
                "symbol": act.symbol,
                "stock_name": act.stock_name or act.symbol,
                "total_qty": 0,
                "total_cost": 0.0,
            }
        h = holdings[act.symbol]
        qty = act.quantity or 0
        if act.action_type == "buy":
            h["total_cost"] += act.price * qty
            h["total_qty"] += qty
        elif act.action_type == "sell":
            if h["total_qty"] > 0:
                avg = h["total_cost"] / h["total_qty"]
                sold = min(qty, h["total_qty"])
                h["total_cost"] -= avg * sold
                h["total_qty"] -= sold

    # Build response
    holding_list = []
    total_cost = 0.0
    for h in holdings.values():
        if h["total_qty"] > 0:
            avg_cost = h["total_cost"] / h["total_qty"] if h["total_qty"] else 0
            holding_list.append({
                "symbol": h["symbol"],
                "stock_name": h["stock_name"],
                "quantity": h["total_qty"],
                "avg_cost": round(avg_cost, 2),
                "last_analysis_date": None,
            })
            total_cost += h["total_cost"]

    return {
        "total_cost": round(total_cost, 2),
        "holding_count": len(holding_list),
        "holdings": holding_list,
    }


async def get_stock_history(
    db: AsyncSession, user_id: uuid.UUID, symbol: str,
) -> list[InvestmentAction]:
    q = (
        select(InvestmentAction)
        .where(InvestmentAction.user_id == user_id)
        .where(InvestmentAction.symbol == symbol)
        .order_by(InvestmentAction.action_date.desc())
    )
    result = await db.execute(q)
    return list(result.scalars().all())
