"""Run CRUD service."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WorkflowRun


async def create_run(
    db: AsyncSession,
    owner_id: uuid.UUID,
    workflow_id: uuid.UUID,
    symbol: str,
    stock_name: str = "",
    config_overrides: dict[str, Any] | None = None,
) -> WorkflowRun:
    run = WorkflowRun(
        owner_id=owner_id,
        workflow_id=workflow_id,
        symbol=symbol,
        stock_name=stock_name,
        status="queued",
        config_overrides=config_overrides or {},
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    return run


async def get_run(db: AsyncSession, run_id: uuid.UUID) -> WorkflowRun | None:
    result = await db.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))
    return result.scalar_one_or_none()


async def list_runs(
    db: AsyncSession, owner_id: uuid.UUID, skip: int = 0, limit: int = 50,
) -> tuple[list[WorkflowRun], int]:
    count_q = select(func.count()).select_from(WorkflowRun).where(WorkflowRun.owner_id == owner_id)
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(WorkflowRun)
        .where(WorkflowRun.owner_id == owner_id)
        .order_by(WorkflowRun.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(q)
    return list(result.scalars().all()), total


async def update_run_status(
    db: AsyncSession, run: WorkflowRun, status: str, **kwargs,
) -> WorkflowRun:
    run.status = status
    for k, v in kwargs.items():
        setattr(run, k, v)
    await db.flush()
    await db.refresh(run)
    return run
