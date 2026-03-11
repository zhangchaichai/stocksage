"""Evolution service: suggestion management."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EvolutionSuggestion
from app.evolution.applier import apply_suggestion


async def list_suggestions(
    db: AsyncSession,
    user_id: uuid.UUID,
    status: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[EvolutionSuggestion], int]:
    base = select(EvolutionSuggestion).where(EvolutionSuggestion.user_id == user_id)
    if status:
        base = base.where(EvolutionSuggestion.status == status)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = base.order_by(EvolutionSuggestion.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all()), total


async def get_suggestion(
    db: AsyncSession, suggestion_id: uuid.UUID,
) -> EvolutionSuggestion | None:
    result = await db.execute(
        select(EvolutionSuggestion).where(EvolutionSuggestion.id == suggestion_id)
    )
    return result.scalar_one_or_none()


async def accept_suggestion(
    db: AsyncSession,
    suggestion: EvolutionSuggestion,
    user_id: uuid.UUID,
) -> bool:
    """Accept and apply a suggestion."""
    success = await apply_suggestion(db, suggestion, user_id)
    if success:
        suggestion.status = "applied"
        suggestion.applied_at = datetime.now(timezone.utc)
    else:
        suggestion.status = "accepted"  # Accepted but application failed
    await db.flush()
    return success


async def reject_suggestion(
    db: AsyncSession,
    suggestion: EvolutionSuggestion,
) -> None:
    suggestion.status = "rejected"
    await db.flush()


async def modify_and_accept(
    db: AsyncSession,
    suggestion: EvolutionSuggestion,
    user_id: uuid.UUID,
    updates: dict[str, Any],
) -> bool:
    """Modify suggestion text/diff and then apply."""
    if "suggestion_text" in updates and updates["suggestion_text"]:
        suggestion.suggestion_text = updates["suggestion_text"]
    if "suggestion_diff" in updates and updates["suggestion_diff"]:
        suggestion.suggestion_diff = updates["suggestion_diff"]
    await db.flush()
    return await accept_suggestion(db, suggestion, user_id)


async def get_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[EvolutionSuggestion], int]:
    """Get applied/rejected suggestions (history)."""
    base = (
        select(EvolutionSuggestion)
        .where(EvolutionSuggestion.user_id == user_id)
        .where(EvolutionSuggestion.status.in_(["applied", "rejected"]))
    )
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = base.order_by(EvolutionSuggestion.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all()), total
