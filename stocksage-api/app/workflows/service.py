"""Workflow CRUD service."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Workflow


async def create_workflow(
    db: AsyncSession, owner_id: uuid.UUID, name: str, description: str,
    definition: dict[str, Any], version: str = "1.0.0", is_public: bool = False,
) -> Workflow:
    wf = Workflow(
        owner_id=owner_id,
        name=name,
        description=description,
        definition=definition,
        version=version,
        is_public=is_public,
    )
    db.add(wf)
    await db.flush()
    await db.refresh(wf)
    return wf


async def get_workflow(db: AsyncSession, workflow_id: uuid.UUID) -> Workflow | None:
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    return result.scalar_one_or_none()


async def list_workflows(
    db: AsyncSession, owner_id: uuid.UUID, skip: int = 0, limit: int = 50,
) -> tuple[list[Workflow], int]:
    count_q = select(func.count()).select_from(Workflow).where(Workflow.owner_id == owner_id)
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(Workflow)
        .where(Workflow.owner_id == owner_id)
        .order_by(Workflow.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(q)
    return list(result.scalars().all()), total


async def update_workflow(
    db: AsyncSession, wf: Workflow, updates: dict[str, Any],
) -> Workflow:
    for k, v in updates.items():
        if v is not None:
            setattr(wf, k, v)
    await db.flush()
    await db.refresh(wf)
    return wf


async def delete_workflow(db: AsyncSession, wf: Workflow) -> None:
    await db.delete(wf)
    await db.flush()
