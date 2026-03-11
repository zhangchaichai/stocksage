"""Memory router: browse, search, manage memory items and categories."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_db
from app.deps import get_current_user
from app.memory.schemas import (
    MemoryCategoryResponse,
    MemoryItemListResponse,
    MemoryItemResponse,
    PreferenceCreate,
    StockMemoryResponse,
    TimelineEntry,
)
from app.memory.service import (
    archive_memory_item,
    get_category_items,
    get_item_categories,
    get_memory_item,
    get_stock_memory,
    get_stock_timeline,
    get_user_preferences,
    list_categories,
    set_user_preference,
)

router = APIRouter()


def _item_to_response(item, categories: list[str] | None = None) -> dict:
    """Convert a MemoryItem ORM object to a response dict."""
    return {
        "id": item.id,
        "memory_type": item.memory_type,
        "content": item.content,
        "structured_data": item.structured_data,
        "importance_weight": item.importance_weight,
        "access_count": item.access_count,
        "happened_at": item.happened_at,
        "is_archived": item.is_archived,
        "categories": categories or [],
        "created_at": item.created_at,
    }


@router.get("/categories", response_model=list[MemoryCategoryResponse])
async def list_my_categories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cats = await list_categories(db, current_user.id)
    return cats


@router.get("/categories/{category_name:path}/items", response_model=MemoryItemListResponse)
async def get_category_items_endpoint(
    category_name: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await get_category_items(db, current_user.id, category_name, skip, limit)
    item_responses = []
    for item in items:
        cats = await get_item_categories(db, item.id)
        item_responses.append(_item_to_response(item, cats))
    return MemoryItemListResponse(items=item_responses, total=total)


@router.get("/items/{item_id}", response_model=MemoryItemResponse)
async def get_memory_item_detail(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await get_memory_item(db, item_id)
    if item is None or item.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Memory item not found")
    cats = await get_item_categories(db, item.id)
    return _item_to_response(item, cats)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory_item(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await get_memory_item(db, item_id)
    if item is None or item.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Memory item not found")
    await archive_memory_item(db, item)


@router.post("/preferences", response_model=MemoryItemResponse)
async def set_preference(
    body: PreferenceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await set_user_preference(db, current_user.id, body.key, body.value, body.category)
    cats = await get_item_categories(db, item.id)
    return _item_to_response(item, cats)


@router.get("/preferences", response_model=list[MemoryItemResponse])
async def get_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await get_user_preferences(db, current_user.id)
    result = []
    for item in items:
        cats = await get_item_categories(db, item.id)
        result.append(_item_to_response(item, cats))
    return result


@router.get("/stock/{symbol}", response_model=StockMemoryResponse)
async def get_stock_memory_endpoint(
    symbol: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memory = await get_stock_memory(db, current_user.id, symbol)

    # Convert ORM objects to response format
    result = {"symbol": symbol, "profile": None, "analysis_events": [], "price_anchors": [], "strategy_reviews": [], "actions": []}
    if memory["profile"]:
        cats = await get_item_categories(db, memory["profile"].id)
        result["profile"] = _item_to_response(memory["profile"], cats)
    for key in ["analysis_events", "price_anchors", "strategy_reviews", "actions"]:
        for item in memory[key]:
            cats = await get_item_categories(db, item.id)
            result[key].append(_item_to_response(item, cats))
    return result


@router.get("/stock/{symbol}/timeline", response_model=list[TimelineEntry])
async def get_stock_timeline_endpoint(
    symbol: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_stock_timeline(db, current_user.id, symbol)


# ---- Semantic search (Phase 4) ----

@router.post("/search")
async def semantic_search(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Search memory items by keyword/semantic query."""
    from app.memory.recall import recall_semantic
    query = body.get("query", "")
    k = body.get("k", 10)
    category = body.get("category")

    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    items = await recall_semantic(db, user.id, query, k, category)
    return [
        {
            "id": str(item.id),
            "memory_type": item.memory_type,
            "content": item.content,
            "structured_data": item.structured_data,
            "importance_weight": item.importance_weight,
            "access_count": item.access_count,
            "happened_at": item.happened_at.isoformat() if item.happened_at else None,
            "is_archived": item.is_archived,
            "created_at": item.created_at.isoformat(),
        }
        for item in items
    ]


@router.post("/forget")
async def run_forgetting(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Run memory forgetting/compression cycle."""
    from app.memory.forgetting import run_forgetting_cycle
    result = await run_forgetting_cycle(db, user.id)
    await db.commit()
    return result
