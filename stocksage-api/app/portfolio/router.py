"""Portfolio router: investment action CRUD + holdings."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_db
from app.deps import get_current_user
from app.portfolio.schemas import (
    ActionCreate,
    ActionListResponse,
    ActionResponse,
    ActionUpdate,
    PortfolioSummary,
)
from app.portfolio.service import (
    create_action,
    delete_action,
    get_action,
    get_portfolio_summary,
    get_stock_history,
    list_actions,
    update_action,
)

router = APIRouter()


@router.post("/actions", response_model=ActionResponse, status_code=status.HTTP_201_CREATED)
async def record_action(
    body: ActionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    action = await create_action(
        db, current_user.id, body.symbol, body.stock_name, body.action_type,
        body.price, body.action_date, body.quantity, body.amount,
        body.reason, body.run_id,
    )
    return action


@router.get("/actions", response_model=ActionListResponse)
async def list_my_actions(
    symbol: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await list_actions(db, current_user.id, symbol, skip, limit)
    return ActionListResponse(items=items, total=total)


@router.get("/actions/{action_id}", response_model=ActionResponse)
async def get_action_detail(
    action_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    action = await get_action(db, action_id)
    if action is None or action.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Action not found")
    return action


@router.put("/actions/{action_id}", response_model=ActionResponse)
async def update_my_action(
    action_id: uuid.UUID,
    body: ActionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    action = await get_action(db, action_id)
    if action is None or action.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Action not found")
    updates = body.model_dump(exclude_unset=True)
    action = await update_action(db, action, updates)
    return action


@router.delete("/actions/{action_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_action(
    action_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    action = await get_action(db, action_id)
    if action is None or action.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Action not found")
    await delete_action(db, action)


@router.get("/summary", response_model=PortfolioSummary)
async def get_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    summary = await get_portfolio_summary(db, current_user.id)
    return summary


@router.get("/holdings")
async def get_holdings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    summary = await get_portfolio_summary(db, current_user.id)
    return summary["holdings"]


@router.get("/{symbol}/history", response_model=list[ActionResponse])
async def get_symbol_history(
    symbol: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    actions = await get_stock_history(db, current_user.id, symbol)
    return actions
