"""Scheduler API router."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.deps import get_current_user, get_db
from app.scheduler import schemas, service

router = APIRouter()


@router.post("/tasks", response_model=schemas.ScheduledTaskResponse, status_code=201)
async def create_task(
    body: schemas.ScheduledTaskCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new scheduled task."""
    task = await service.create_task(
        db,
        user_id=user.id,
        name=body.name,
        task_type=body.task_type,
        cron_expr=body.cron_expr,
        timezone=body.timezone,
        enabled=body.enabled,
        config=body.config,
    )
    await db.commit()

    # Register with the running scheduler
    from app.scheduler.worker import register_task
    register_task(task)

    return task


@router.get("/tasks", response_model=list[schemas.ScheduledTaskResponse])
async def list_tasks(
    enabled_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List scheduled tasks for the current user."""
    items, _ = await service.list_tasks(db, user.id, enabled_only, skip, limit)
    return items


@router.get("/tasks/{task_id}", response_model=schemas.ScheduledTaskResponse)
async def get_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a specific scheduled task."""
    task = await service.get_task(db, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return task


@router.patch("/tasks/{task_id}", response_model=schemas.ScheduledTaskResponse)
async def update_task(
    task_id: uuid.UUID,
    body: schemas.ScheduledTaskUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update a scheduled task."""
    task = await service.get_task(db, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="Scheduled task not found")

    update_fields = body.model_dump(exclude_none=True)
    task = await service.update_task(db, task, **update_fields)
    await db.commit()

    # Re-register with the scheduler
    from app.scheduler.worker import register_task
    register_task(task)

    return task


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a scheduled task."""
    task = await service.get_task(db, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="Scheduled task not found")

    # Unregister from the scheduler
    from app.scheduler.worker import unregister_task
    unregister_task(str(task.id))

    await service.delete_task(db, task)
    await db.commit()


@router.post("/tasks/{task_id}/trigger", response_model=schemas.ScheduledTaskResponse)
async def trigger_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Manually trigger a scheduled task immediately."""
    task = await service.get_task(db, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="Scheduled task not found")

    from app.scheduler.worker import trigger_task_now
    trigger_task_now(str(task.id))

    return task
