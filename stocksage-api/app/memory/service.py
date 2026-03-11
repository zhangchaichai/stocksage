"""Memory service: CRUD + category management."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import MemoryCategory, MemoryCategoryItem, MemoryItem, MemoryResource


# ---- Default categories ----

DEFAULT_CATEGORIES = [
    {"name": "user/investment_style", "description": "用户投资风格偏好（价值/成长/动量/短线）"},
    {"name": "user/risk_appetite", "description": "用户风险承受能力与偏好"},
    {"name": "user/portfolio", "description": "用户持仓与关注列表"},
    {"name": "user/feedback", "description": "用户对分析结果的反馈"},
    {"name": "strategy/patterns", "description": "已验证的分析规律与策略规则"},
    {"name": "strategy/mistakes", "description": "历史分析错误与教训总结"},
    {"name": "macro/monetary_policy", "description": "货币政策相关记忆（利率、流动性、央行动态）"},
    {"name": "macro/economic_cycle", "description": "经济周期跟踪与评估"},
]


async def ensure_default_categories(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Create default categories for a user if they don't exist."""
    for cat_def in DEFAULT_CATEGORIES:
        existing = await db.execute(
            select(MemoryCategory)
            .where(MemoryCategory.user_id == user_id)
            .where(MemoryCategory.name == cat_def["name"])
        )
        if existing.scalar_one_or_none() is None:
            cat = MemoryCategory(
                user_id=user_id,
                name=cat_def["name"],
                description=cat_def["description"],
            )
            db.add(cat)
    await db.flush()


async def get_or_create_category(
    db: AsyncSession, user_id: uuid.UUID, name: str, description: str = "",
) -> MemoryCategory:
    """Get existing category or create a new one."""
    result = await db.execute(
        select(MemoryCategory)
        .where(MemoryCategory.user_id == user_id)
        .where(MemoryCategory.name == name)
    )
    cat = result.scalar_one_or_none()
    if cat is None:
        cat = MemoryCategory(user_id=user_id, name=name, description=description)
        db.add(cat)
        await db.flush()
        await db.refresh(cat)
    return cat


async def create_memory_item(
    db: AsyncSession,
    user_id: uuid.UUID,
    memory_type: str,
    content: str,
    structured_data: dict[str, Any] | None = None,
    importance_weight: float = 0.5,
    happened_at=None,
    resource_id: uuid.UUID | None = None,
    category_names: list[str] | None = None,
) -> MemoryItem:
    """Create a memory item and link it to categories."""
    item = MemoryItem(
        user_id=user_id,
        resource_id=resource_id,
        memory_type=memory_type,
        content=content,
        structured_data=structured_data,
        importance_weight=importance_weight,
        happened_at=happened_at,
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)

    # Link to categories
    if category_names:
        for cat_name in category_names:
            cat = await get_or_create_category(db, user_id, cat_name)
            link = MemoryCategoryItem(item_id=item.id, category_id=cat.id)
            db.add(link)
        await db.flush()

    return item


async def list_categories(
    db: AsyncSession, user_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """List all categories for a user with item counts."""
    await ensure_default_categories(db, user_id)

    cats = await db.execute(
        select(MemoryCategory).where(MemoryCategory.user_id == user_id).order_by(MemoryCategory.name)
    )
    categories = list(cats.scalars().all())

    result = []
    for cat in categories:
        count_q = select(func.count()).select_from(MemoryCategoryItem).where(
            MemoryCategoryItem.category_id == cat.id
        )
        count = (await db.execute(count_q)).scalar() or 0
        result.append({
            "id": cat.id,
            "name": cat.name,
            "description": cat.description,
            "summary": cat.summary,
            "item_count": count,
        })
    return result


async def get_category_items(
    db: AsyncSession, user_id: uuid.UUID, category_name: str,
    skip: int = 0, limit: int = 20,
) -> tuple[list[MemoryItem], int]:
    """Get memory items in a specific category."""
    cat = await db.execute(
        select(MemoryCategory)
        .where(MemoryCategory.user_id == user_id)
        .where(MemoryCategory.name == category_name)
    )
    category = cat.scalar_one_or_none()
    if category is None:
        return [], 0

    base = (
        select(MemoryItem)
        .join(MemoryCategoryItem, MemoryCategoryItem.item_id == MemoryItem.id)
        .where(MemoryCategoryItem.category_id == category.id)
        .where(MemoryItem.is_archived == False)
    )
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = base.order_by(MemoryItem.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    items = list(result.scalars().all())

    return items, total


async def get_memory_item(db: AsyncSession, item_id: uuid.UUID) -> MemoryItem | None:
    result = await db.execute(select(MemoryItem).where(MemoryItem.id == item_id))
    return result.scalar_one_or_none()


async def archive_memory_item(db: AsyncSession, item: MemoryItem) -> None:
    """Soft-delete: mark as archived."""
    item.is_archived = True
    await db.flush()


async def get_item_categories(db: AsyncSession, item_id: uuid.UUID) -> list[str]:
    """Get category names for a memory item."""
    q = (
        select(MemoryCategory.name)
        .join(MemoryCategoryItem, MemoryCategoryItem.category_id == MemoryCategory.id)
        .where(MemoryCategoryItem.item_id == item_id)
    )
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_stock_memory(
    db: AsyncSession, user_id: uuid.UUID, symbol: str,
) -> dict[str, Any]:
    """Get complete memory for a stock."""
    cat_name = f"stock/{symbol}"
    cat_result = await db.execute(
        select(MemoryCategory)
        .where(MemoryCategory.user_id == user_id)
        .where(MemoryCategory.name == cat_name)
    )
    category = cat_result.scalar_one_or_none()

    result: dict[str, Any] = {
        "symbol": symbol,
        "profile": None,
        "analysis_events": [],
        "price_anchors": [],
        "strategy_reviews": [],
        "actions": [],
    }

    if category is None:
        return result

    items_q = (
        select(MemoryItem)
        .join(MemoryCategoryItem, MemoryCategoryItem.item_id == MemoryItem.id)
        .where(MemoryCategoryItem.category_id == category.id)
        .where(MemoryItem.is_archived == False)
        .order_by(MemoryItem.created_at.desc())
    )
    items = (await db.execute(items_q)).scalars().all()

    for item in items:
        if item.memory_type == "stock_profile":
            result["profile"] = item
        elif item.memory_type == "analysis_event":
            result["analysis_events"].append(item)
        elif item.memory_type == "price_anchor":
            result["price_anchors"].append(item)
        elif item.memory_type == "strategy_review":
            result["strategy_reviews"].append(item)
        elif item.memory_type == "investment_action":
            result["actions"].append(item)

    return result


async def get_stock_timeline(
    db: AsyncSession, user_id: uuid.UUID, symbol: str,
) -> list[dict[str, Any]]:
    """Get timeline view for a stock."""
    cat_name = f"stock/{symbol}"
    cat_result = await db.execute(
        select(MemoryCategory)
        .where(MemoryCategory.user_id == user_id)
        .where(MemoryCategory.name == cat_name)
    )
    category = cat_result.scalar_one_or_none()
    if category is None:
        return []

    items_q = (
        select(MemoryItem)
        .join(MemoryCategoryItem, MemoryCategoryItem.item_id == MemoryItem.id)
        .where(MemoryCategoryItem.category_id == category.id)
        .where(MemoryItem.is_archived == False)
        .order_by(MemoryItem.happened_at.desc().nullslast(), MemoryItem.created_at.desc())
    )
    items = (await db.execute(items_q)).scalars().all()

    timeline = []
    for item in items:
        date = item.happened_at or item.created_at
        timeline.append({
            "date": date.isoformat() if date else "",
            "type": item.memory_type,
            "content": item.content,
            "structured_data": item.structured_data,
        })
    return timeline


async def set_user_preference(
    db: AsyncSession, user_id: uuid.UUID, key: str, value: str, category: str,
) -> MemoryItem:
    """Set a user preference (active memory)."""
    return await create_memory_item(
        db, user_id,
        memory_type="user_preference",
        content=f"{key}: {value}",
        structured_data={"key": key, "value": value},
        importance_weight=0.9,
        category_names=[category],
    )


async def get_user_preferences(
    db: AsyncSession, user_id: uuid.UUID,
) -> list[MemoryItem]:
    """Get user preference memory items."""
    q = (
        select(MemoryItem)
        .where(MemoryItem.user_id == user_id)
        .where(MemoryItem.memory_type == "user_preference")
        .where(MemoryItem.is_archived == False)
        .order_by(MemoryItem.created_at.desc())
    )
    result = await db.execute(q)
    return list(result.scalars().all())
