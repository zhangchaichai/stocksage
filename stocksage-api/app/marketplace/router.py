"""Marketplace router: browse, star, fork, publish skills."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CustomSkill, SkillStar, User
from app.db.session import get_db
from app.deps import get_current_user, get_current_user_optional
from app.marketplace.schemas import MarketplaceListResponse, MarketplaceSkillResponse
from app.marketplace.service import (
    fork_skill,
    list_marketplace_skills,
    publish_skill,
    toggle_star,
)
from sqlalchemy import select

router = APIRouter()


@router.get("/skills", response_model=MarketplaceListResponse)
async def list_skills(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None),
    type: str | None = Query(None),
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """List published skills. Auth is optional (used for starred_by_me)."""
    items, total = await list_marketplace_skills(db, skip, limit, search, type)

    # Determine which skills are starred by current user
    starred_ids: set[uuid.UUID] = set()
    if current_user is not None:
        skill_ids = [s.id for s in items]
        if skill_ids:
            result = await db.execute(
                select(SkillStar.skill_id).where(
                    SkillStar.user_id == current_user.id,
                    SkillStar.skill_id.in_(skill_ids),
                )
            )
            starred_ids = {row[0] for row in result.all()}

    response_items = []
    for skill in items:
        owner_username = ""
        if skill.owner:
            owner_username = skill.owner.username
        response_items.append(
            MarketplaceSkillResponse(
                id=skill.id,
                owner_id=skill.owner_id,
                owner_username=owner_username,
                name=skill.name,
                version=skill.version,
                type=skill.type,
                tags=skill.tags,
                definition_md=skill.definition_md,
                is_published=skill.is_published,
                stars_count=skill.stars_count,
                starred_by_me=skill.id in starred_ids,
                created_at=skill.created_at,
                updated_at=skill.updated_at,
            )
        )

    return MarketplaceListResponse(items=response_items, total=total)


@router.post("/skills/{skill_id}/star")
async def star_skill(
    skill_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle star on a skill. Returns whether the skill is now starred."""
    skill = await db.get(CustomSkill, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    starred = await toggle_star(db, skill_id, current_user.id)
    await db.refresh(skill)
    return {"starred": starred, "stars_count": skill.stars_count}


@router.post("/skills/{skill_id}/fork")
async def fork_existing_skill(
    skill_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fork a published skill to your namespace."""
    skill = await db.get(CustomSkill, skill_id)
    if skill is None or not skill.is_published:
        raise HTTPException(status_code=404, detail="Published skill not found")
    try:
        forked = await fork_skill(db, skill_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "id": forked.id,
        "name": forked.name,
        "forked_from": forked.forked_from,
    }


@router.post("/skills/{skill_id}/publish")
async def publish_own_skill(
    skill_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Publish your own skill to the marketplace."""
    try:
        skill = await publish_skill(db, skill_id, current_user.id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Skill not found")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not the owner of this skill")
    return {"id": skill.id, "is_published": skill.is_published}
