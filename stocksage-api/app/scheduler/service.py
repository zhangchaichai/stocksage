"""Scheduler service: CRUD for scheduled tasks."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ScheduledTask


async def create_task(
    db: AsyncSession,
    user_id: uuid.UUID,
    name: str,
    task_type: str,
    cron_expr: str,
    timezone: str = "Asia/Shanghai",
    enabled: bool = True,
    config: dict[str, Any] | None = None,
) -> ScheduledTask:
    """Create a new scheduled task."""
    task = ScheduledTask(
        user_id=user_id,
        name=name,
        task_type=task_type,
        cron_expr=cron_expr,
        timezone=timezone,
        enabled=enabled,
        config=config or {},
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


async def update_task(
    db: AsyncSession,
    task: ScheduledTask,
    **kwargs,
) -> ScheduledTask:
    """Update an existing scheduled task."""
    for key, value in kwargs.items():
        if value is not None and hasattr(task, key):
            setattr(task, key, value)
    await db.flush()
    await db.refresh(task)
    return task


async def delete_task(db: AsyncSession, task: ScheduledTask) -> None:
    """Delete a scheduled task."""
    await db.delete(task)
    await db.flush()


async def get_task(
    db: AsyncSession,
    task_id: uuid.UUID,
) -> ScheduledTask | None:
    """Get a task by ID."""
    result = await db.execute(
        select(ScheduledTask).where(ScheduledTask.id == task_id)
    )
    return result.scalar_one_or_none()


async def list_tasks(
    db: AsyncSession,
    user_id: uuid.UUID,
    enabled_only: bool = False,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[ScheduledTask], int]:
    """List scheduled tasks for a user."""
    base = select(ScheduledTask).where(ScheduledTask.user_id == user_id)
    if enabled_only:
        base = base.where(ScheduledTask.enabled == True)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = base.order_by(ScheduledTask.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all()), total


async def list_enabled_tasks(db: AsyncSession) -> list[ScheduledTask]:
    """List all enabled tasks across all users (for the scheduler worker)."""
    result = await db.execute(
        select(ScheduledTask).where(ScheduledTask.enabled == True)
    )
    return list(result.scalars().all())
