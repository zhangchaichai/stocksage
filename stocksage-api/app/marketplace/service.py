"""Marketplace service: list, star, fork, publish skills."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.models import CustomSkill, SkillStar


async def list_marketplace_skills(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    skill_type: str | None = None,
) -> tuple[list[CustomSkill], int]:
    """Query published skills with optional text search on name and type filter."""
    base = select(CustomSkill).where(CustomSkill.is_published == True)  # noqa: E712

    if search:
        base = base.where(CustomSkill.name.ilike(f"%{search}%"))
    if skill_type:
        base = base.where(CustomSkill.type == skill_type)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = base.options(joinedload(CustomSkill.owner)).order_by(CustomSkill.stars_count.desc(), CustomSkill.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().unique().all()), total


async def toggle_star(
    db: AsyncSession,
    skill_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Insert SkillStar if not exists (return True), delete if exists (return False).

    Also updates stars_count on CustomSkill.
    """
    existing = await db.execute(
        select(SkillStar).where(
            SkillStar.skill_id == skill_id,
            SkillStar.user_id == user_id,
        )
    )
    star = existing.scalar_one_or_none()

    if star is not None:
        # Unstar
        await db.execute(
            delete(SkillStar).where(SkillStar.id == star.id)
        )
        # Decrement stars_count
        skill = await db.get(CustomSkill, skill_id)
        if skill:
            skill.stars_count = max(0, (skill.stars_count or 0) - 1)
        await db.flush()
        return False
    else:
        # Star
        new_star = SkillStar(skill_id=skill_id, user_id=user_id)
        db.add(new_star)
        # Increment stars_count
        skill = await db.get(CustomSkill, skill_id)
        if skill:
            skill.stars_count = (skill.stars_count or 0) + 1
        await db.flush()
        return True


async def fork_skill(
    db: AsyncSession,
    skill_id: uuid.UUID,
    user_id: uuid.UUID,
) -> CustomSkill:
    """Copy a published skill to user's namespace with forked_from set."""
    original = await db.get(CustomSkill, skill_id)
    if original is None:
        raise ValueError("Skill not found")

    forked = CustomSkill(
        owner_id=user_id,
        name=f"{original.name} (fork)",
        version=original.version,
        type=original.type,
        tags=original.tags if original.tags else [],
        definition_md=original.definition_md,
        is_published=False,
        forked_from=original.id,
        stars_count=0,
    )
    db.add(forked)
    await db.flush()
    await db.refresh(forked)
    return forked


async def publish_skill(
    db: AsyncSession,
    skill_id: uuid.UUID,
    user_id: uuid.UUID,
) -> CustomSkill:
    """Set is_published=True on user's own skill."""
    skill = await db.get(CustomSkill, skill_id)
    if skill is None:
        raise ValueError("Skill not found")
    if skill.owner_id != user_id:
        raise PermissionError("Not the owner of this skill")

    skill.is_published = True
    await db.flush()
    await db.refresh(skill)
    return skill
