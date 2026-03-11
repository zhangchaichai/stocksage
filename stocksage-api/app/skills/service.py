"""Skill CRUD service."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CustomSkill


async def create_skill(
    db: AsyncSession, owner_id: uuid.UUID, name: str, version: str,
    skill_type: str, tags: list[str], definition_md: str,
) -> CustomSkill:
    skill = CustomSkill(
        owner_id=owner_id,
        name=name,
        version=version,
        type=skill_type,
        tags=tags,
        definition_md=definition_md,
    )
    db.add(skill)
    await db.flush()
    await db.refresh(skill)
    return skill


async def get_skill(db: AsyncSession, skill_id: uuid.UUID) -> CustomSkill | None:
    result = await db.execute(select(CustomSkill).where(CustomSkill.id == skill_id))
    return result.scalar_one_or_none()


async def list_skills(
    db: AsyncSession, owner_id: uuid.UUID, skip: int = 0, limit: int = 50,
) -> tuple[list[CustomSkill], int]:
    count_q = select(func.count()).select_from(CustomSkill).where(CustomSkill.owner_id == owner_id)
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(CustomSkill)
        .where(CustomSkill.owner_id == owner_id)
        .order_by(CustomSkill.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(q)
    return list(result.scalars().all()), total


async def update_skill(
    db: AsyncSession, skill: CustomSkill, updates: dict[str, Any],
) -> CustomSkill:
    for k, v in updates.items():
        if v is not None:
            setattr(skill, k, v)
    await db.flush()
    await db.refresh(skill)
    return skill


async def delete_skill(db: AsyncSession, skill: CustomSkill) -> None:
    await db.delete(skill)
    await db.flush()
