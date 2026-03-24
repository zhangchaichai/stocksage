"""Memory forgetting and compression mechanisms.

Implements memory value scoring and archival/compression for old entries.
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func as sa_func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MemoryCategory, MemoryCategoryItem, MemoryItem
from app.memory import MEMORY_TYPE_WEIGHTS

logger = logging.getLogger(__name__)


def calculate_memory_value(item: MemoryItem) -> float:
    """Calculate memory value score.

    MemoryValue = alpha * RecencyScore + beta * FrequencyScore + gamma * ImportanceScore
    alpha=0.3, beta=0.3, gamma=0.4
    """
    now = datetime.now(timezone.utc)

    # Recency score
    last_access = item.last_accessed_at or item.created_at
    if last_access.tzinfo is None:
        last_access = last_access.replace(tzinfo=timezone.utc)
    days_since = max((now - last_access).days, 0)
    recency_score = 1.0 / (1.0 + days_since)

    # Frequency score
    frequency_score = min(item.access_count / 10.0, 1.0)

    # Importance score
    importance_score = MEMORY_TYPE_WEIGHTS.get(item.memory_type, 0.5)

    return 0.3 * recency_score + 0.3 * frequency_score + 0.4 * importance_score


async def compress_old_events(
    db: AsyncSession,
    user_id: uuid.UUID,
    category_name: str,
    threshold: int = 20,
) -> int:
    """Compress old analysis_events when a category exceeds threshold.

    - Keep the most recent 5 entries intact
    - Archive older entries (mark is_archived=True)

    Returns number of archived items.
    """
    # Find category
    cat_q = (
        select(MemoryCategory)
        .where(MemoryCategory.user_id == user_id)
        .where(MemoryCategory.name == category_name)
    )
    cat = (await db.execute(cat_q)).scalar_one_or_none()
    if not cat:
        return 0

    # Count analysis_events in this category
    count_q = (
        select(sa_func.count())
        .select_from(MemoryItem)
        .join(MemoryCategoryItem, MemoryCategoryItem.item_id == MemoryItem.id)
        .where(MemoryCategoryItem.category_id == cat.id)
        .where(MemoryItem.memory_type == "analysis_event")
        .where(MemoryItem.is_archived == False)
    )
    count = (await db.execute(count_q)).scalar() or 0

    if count <= threshold:
        return 0

    # Get items ordered by date, skip the newest 5
    items_q = (
        select(MemoryItem)
        .join(MemoryCategoryItem, MemoryCategoryItem.item_id == MemoryItem.id)
        .where(MemoryCategoryItem.category_id == cat.id)
        .where(MemoryItem.memory_type == "analysis_event")
        .where(MemoryItem.is_archived == False)
        .order_by(desc(MemoryItem.created_at))
        .offset(5)  # Skip newest 5
    )
    old_items = (await db.execute(items_q)).scalars().all()

    archived = 0
    for item in old_items:
        item.is_archived = True
        archived += 1

    if archived > 0:
        await db.flush()
        logger.info("Archived %d old analysis_events for %s", archived, category_name)

    return archived


async def archive_expired_anchors(
    db: AsyncSession,
    user_id: uuid.UUID,
    max_age_days: int = 365,
) -> int:
    """Archive price_anchors older than max_age_days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    q = (
        select(MemoryItem)
        .where(MemoryItem.user_id == user_id)
        .where(MemoryItem.memory_type == "price_anchor")
        .where(MemoryItem.is_archived == False)
        .where(MemoryItem.created_at < cutoff)
    )
    items = (await db.execute(q)).scalars().all()

    archived = 0
    for item in items:
        item.is_archived = True
        archived += 1

    if archived > 0:
        await db.flush()
        logger.info("Archived %d expired price_anchors for user %s", archived, user_id)

    return archived


async def run_forgetting_cycle(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict[str, int]:
    """Run a full forgetting cycle for a user.

    - Compress old events in each stock category
    - Archive expired price anchors
    """
    results = {"compressed": 0, "expired_anchors": 0}

    # Find all stock categories
    cats_q = (
        select(MemoryCategory)
        .where(MemoryCategory.user_id == user_id)
        .where(MemoryCategory.name.like("stock/%"))
    )
    cats = (await db.execute(cats_q)).scalars().all()

    for cat in cats:
        compressed = await compress_old_events(db, user_id, cat.name)
        results["compressed"] += compressed

    # Archive expired anchors
    results["expired_anchors"] = await archive_expired_anchors(db, user_id)

    return results
