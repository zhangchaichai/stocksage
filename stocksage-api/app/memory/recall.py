"""Memory recall: three-mode retrieval for workflow context injection.

Mode A: Default category recall (SQL, millisecond-level)
Mode B: Related category discovery (future: vector search)
Mode C: Semantic memory retrieval (future: vector search)

Phase 4 base implementation uses SQL-based recall. Vector search will be
added when pgvector is set up.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
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

            # Update access tracking
            item.access_count += 1
            item.last_accessed_at = datetime.now(timezone.utc)

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
    # Use SQL LIKE for basic search (escape wildcards in user input)
    from sqlalchemy import or_, func as sa_func
    conditions = []
    for kw in keywords:
        # Escape SQL LIKE wildcards: % and _
        escaped = kw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(MemoryItem.content.ilike(f"%{escaped}%", escape="\\"))

    if conditions:
        base = base.where(or_(*conditions))

    q = base.order_by(desc(MemoryItem.created_at)).limit(k)
    result = await db.execute(q)
    items = list(result.scalars().all())

    # Update access tracking
    for item in items:
        item.access_count += 1
        item.last_accessed_at = datetime.now(timezone.utc)
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


# ============================================================
# Compact memory format for token-efficient workflow injection
# ============================================================


def _compact_analysis_summary(analysis: dict | None) -> str:
    """Compress an analysis_event into a single-line summary (~30 tokens)."""
    if not analysis:
        return ""
    date = analysis.get("date", "?")
    data = analysis.get("data", {})
    if not isinstance(data, dict):
        data = {}
    rec = data.get("recommendation", "?")
    conf = data.get("confidence", "?")
    logic = data.get("core_logic", "")
    if len(logic) > 50:
        logic = logic[:50] + "..."
    return f"上次分析({date}): {rec}, 置信度{conf}, 逻辑: {logic}"


def _compact_review_stats(reviews: list[dict]) -> str:
    """Compress strategy_reviews into a statistical summary (~20 tokens)."""
    if not reviews:
        return ""
    total = len(reviews)
    correct = sum(
        1 for r in reviews
        if isinstance(r.get("data"), dict) and r["data"].get("direction_correct")
    )
    acc = round(correct / total * 100) if total else 0
    return f"历史复盘: {total}次, 方向准确率{acc}%"


def _compact_recent_directions(analyses: list[dict]) -> str:
    """Compress recent_analyses into a direction list (~30 tokens)."""
    if not analyses:
        return ""
    parts = []
    for a in analyses[:3]:
        date = a.get("date", "?")
        data = a.get("data", {})
        if not isinstance(data, dict):
            data = {}
        rec = data.get("recommendation", "?")
        parts.append(f"{date}:{rec}")
    return "近期方向: " + ", ".join(parts)


async def recall_memory_compact(
    db: AsyncSession,
    user_id: uuid.UUID,
    symbol: str,
) -> dict[str, Any]:
    """Token-efficient memory recall for workflow injection.

    Returns pre-compressed summaries instead of full structured data.
    Total token cost: ~50-150 tokens (vs ~1,080 for full recall).

    Keys returned:
    - last_analysis_summary: str  (~30 tokens)
    - review_stats: str           (~20 tokens)
    - recent_directions: str      (~30 tokens)
    - portfolio_position: dict|None (~20 tokens)
    - profile_name: str           (~10 tokens)
    """
    full = await recall_memory(db, user_id, symbol)

    compact: dict[str, Any] = {
        "symbol": symbol,
        "last_analysis_summary": _compact_analysis_summary(full.get("last_analysis")),
        "review_stats": _compact_review_stats(full.get("strategy_reviews", [])),
        "recent_directions": _compact_recent_directions(full.get("recent_analyses", [])),
        "portfolio_position": full.get("portfolio_position"),
        "profile_name": "",
    }

    profile = full.get("profile")
    if isinstance(profile, dict) and profile.get("data"):
        pdata = profile["data"]
        if isinstance(pdata, dict):
            compact["profile_name"] = pdata.get("stock_name", "")

    return compact
