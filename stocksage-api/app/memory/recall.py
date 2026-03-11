"""Memory recall: three-mode retrieval for workflow context injection.

Mode A: Default category recall (SQL, millisecond-level)
Mode B: Related category discovery (future: vector search)
Mode C: Semantic memory retrieval (future: vector search)

Phase 4 base implementation uses SQL-based recall. Vector search will be
added when pgvector is set up.
"""
from __future__ import annotations
import uuid
from typing import Any

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    InvestmentAction,
    MemoryCategory,
    MemoryCategoryItem,
    MemoryItem,
)


async def recall_default(
    db: AsyncSession,
    user_id: uuid.UUID,
    symbol: str,
) -> dict[str, Any]:
    """Mode A: Recall default memory context for a stock analysis.

    Retrieves:
    - Latest 3 analysis_events for this stock
    - stock_profile if exists
    - Latest price_anchors
    - Latest strategy_reviews
    - Current portfolio position
    """
    cat_name = f"stock/{symbol}"

    # Find the stock category
    cat_result = await db.execute(
        select(MemoryCategory)
        .where(MemoryCategory.user_id == user_id)
        .where(MemoryCategory.name == cat_name)
    )
    category = cat_result.scalar_one_or_none()

    context: dict[str, Any] = {
        "symbol": symbol,
        "profile": None,
        "last_analysis": None,
        "recent_analyses": [],
        "price_anchors": [],
        "strategy_reviews": [],
        "portfolio_position": None,
    }

    if category:
        # Get items in this category
        items_q = (
            select(MemoryItem)
            .join(MemoryCategoryItem, MemoryCategoryItem.item_id == MemoryItem.id)
            .where(MemoryCategoryItem.category_id == category.id)
            .where(MemoryItem.is_archived == False)
            .order_by(desc(MemoryItem.created_at))
        )
        items = (await db.execute(items_q)).scalars().all()

        analyses = []
        for item in items:
            if item.memory_type == "stock_profile" and context["profile"] is None:
                context["profile"] = {
                    "content": item.content,
                    "data": item.structured_data,
                }
            elif item.memory_type == "analysis_event":
                analyses.append({
                    "date": item.happened_at.isoformat() if item.happened_at else "",
                    "content": item.content,
                    "data": item.structured_data,
                })
            elif item.memory_type == "price_anchor":
                context["price_anchors"].append({
                    "content": item.content,
                    "data": item.structured_data,
                })
            elif item.memory_type == "strategy_review":
                context["strategy_reviews"].append({
                    "content": item.content,
                    "data": item.structured_data,
                })

            # Update access count
            item.access_count += 1

        # Keep only recent 3 analyses
        context["recent_analyses"] = analyses[:3]
        if analyses:
            context["last_analysis"] = analyses[0]

        await db.flush()

    # Get portfolio position
    actions_q = (
        select(InvestmentAction)
        .where(InvestmentAction.user_id == user_id)
        .where(InvestmentAction.symbol == symbol)
        .where(InvestmentAction.action_type.in_(["buy", "sell"]))
        .order_by(InvestmentAction.action_date.asc())
    )
    actions = (await db.execute(actions_q)).scalars().all()

    total_qty = 0
    total_cost = 0.0
    for act in actions:
        qty = act.quantity or 0
        if act.action_type == "buy":
            total_cost += act.price * qty
            total_qty += qty
        elif act.action_type == "sell":
            if total_qty > 0:
                avg = total_cost / total_qty
                sold = min(qty, total_qty)
                total_cost -= avg * sold
                total_qty -= sold

    if total_qty > 0:
        context["portfolio_position"] = {
            "quantity": total_qty,
            "avg_cost": round(total_cost / total_qty, 2) if total_qty else 0,
            "total_cost": round(total_cost, 2),
        }

    return context


async def recall_related_categories(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    k: int = 5,
) -> list[dict[str, Any]]:
    """Mode B: Discover related categories.

    Phase 4 base: Simple keyword matching on category names and descriptions.
    Future: Vector similarity search on category embeddings.
    """
    keywords = query.lower().split()

    cats_q = (
        select(MemoryCategory)
        .where(MemoryCategory.user_id == user_id)
        .order_by(MemoryCategory.name)
    )
    cats = (await db.execute(cats_q)).scalars().all()

    scored = []
    for cat in cats:
        score = 0
        cat_text = f"{cat.name} {cat.description}".lower()
        for kw in keywords:
            if kw in cat_text:
                score += 1
        if score > 0:
            scored.append((score, cat))

    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {
            "id": str(cat.id),
            "name": cat.name,
            "description": cat.description,
            "score": score,
        }
        for score, cat in scored[:k]
    ]


async def recall_semantic(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    k: int = 10,
    category: str | None = None,
) -> list[MemoryItem]:
    """Mode C: Semantic memory retrieval.

    Phase 4 base: Simple keyword search in content.
    Future: Vector similarity search on item embeddings.
    """
    base = (
        select(MemoryItem)
        .where(MemoryItem.user_id == user_id)
        .where(MemoryItem.is_archived == False)
    )

    if category:
        base = (
            base
            .join(MemoryCategoryItem, MemoryCategoryItem.item_id == MemoryItem.id)
            .join(MemoryCategory, MemoryCategory.id == MemoryCategoryItem.category_id)
            .where(MemoryCategory.name == category)
        )

    # Simple keyword search
    keywords = query.lower().split()
    # Use SQL LIKE for basic search
    from sqlalchemy import or_, func as sa_func
    conditions = []
    for kw in keywords:
        conditions.append(MemoryItem.content.ilike(f"%{kw}%"))

    if conditions:
        base = base.where(or_(*conditions))

    q = base.order_by(desc(MemoryItem.created_at)).limit(k)
    result = await db.execute(q)
    items = list(result.scalars().all())

    # Update access counts
    for item in items:
        item.access_count += 1
    if items:
        await db.flush()

    return items


async def recall_memory(
    db: AsyncSession,
    user_id: uuid.UUID,
    symbol: str,
) -> dict[str, Any]:
    """Full memory recall for workflow injection.

    Combines Mode A (default recall) with Mode B (related categories).
    """
    # Mode A: Default context
    context = await recall_default(db, user_id, symbol)

    # Mode B: Find related categories
    query = f"{symbol} stock analysis"
    related = await recall_related_categories(db, user_id, query, k=3)
    context["related_categories"] = related

    return context
