"""Memory extractors: extract MemoryItems from WorkflowRun results."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.service import create_memory_item, get_or_create_category


# memory_type importance weights
IMPORTANCE_WEIGHTS: dict[str, float] = {
    "stock_profile": 0.9,
    "analysis_event": 0.6,
    "market_event": 0.7,
    "price_anchor": 0.5,
    "strategy_review": 0.8,
    "user_preference": 0.9,
    "portfolio_context": 0.4,
    "industry_insight": 0.6,
    "investment_action": 0.7,
}


async def extract_analysis_event(
    db: AsyncSession,
    user_id: uuid.UUID,
    symbol: str,
    run_result: dict[str, Any],
    happened_at: datetime | None = None,
    resource_id: uuid.UUID | None = None,
) -> None:
    """Extract analysis_event memory from a completed workflow run result."""
    decision = run_result.get("decision", {})
    if not decision:
        return

    recommendation = decision.get("recommendation", "UNKNOWN")
    confidence = decision.get("confidence", 0)
    target_price = decision.get("target_price", {})
    core_logic = decision.get("core_logic", "")

    content = (
        f"{happened_at.strftime('%Y-%m-%d') if happened_at else 'N/A'} "
        f"Analysis: {recommendation}, confidence {confidence}"
    )
    if target_price:
        content += f", target {target_price}"
    if core_logic:
        content += f", logic: {core_logic}"

    structured = {
        "recommendation": recommendation,
        "confidence": confidence,
        "target_price": target_price,
        "core_logic": core_logic,
    }

    # Extract dimension scores if available
    dim_scores = decision.get("dimension_scores", {})
    if dim_scores:
        structured["dimension_scores"] = dim_scores

    await create_memory_item(
        db, user_id,
        memory_type="analysis_event",
        content=content,
        structured_data=structured,
        importance_weight=IMPORTANCE_WEIGHTS["analysis_event"],
        happened_at=happened_at or datetime.now(timezone.utc),
        resource_id=resource_id,
        category_names=[f"stock/{symbol}"],
    )


async def extract_stock_profile(
    db: AsyncSession,
    user_id: uuid.UUID,
    symbol: str,
    stock_name: str,
    run_result: dict[str, Any],
    resource_id: uuid.UUID | None = None,
) -> None:
    """Extract or update stock_profile memory (basic company info)."""
    from sqlalchemy import select
    from app.db.models import MemoryItem, MemoryCategoryItem, MemoryCategory

    # Check if profile already exists
    cat_name = f"stock/{symbol}"
    cat_result = await db.execute(
        select(MemoryCategory)
        .where(MemoryCategory.user_id == user_id)
        .where(MemoryCategory.name == cat_name)
    )
    category = cat_result.scalar_one_or_none()

    if category:
        existing = await db.execute(
            select(MemoryItem)
            .join(MemoryCategoryItem, MemoryCategoryItem.item_id == MemoryItem.id)
            .where(MemoryCategoryItem.category_id == category.id)
            .where(MemoryItem.memory_type == "stock_profile")
            .where(MemoryItem.is_archived == False)
        )
        if existing.scalar_one_or_none():
            return  # Profile already exists, skip

    content = f"{symbol} ({stock_name})"
    await create_memory_item(
        db, user_id,
        memory_type="stock_profile",
        content=content,
        structured_data={"symbol": symbol, "stock_name": stock_name},
        importance_weight=IMPORTANCE_WEIGHTS["stock_profile"],
        resource_id=resource_id,
        category_names=[cat_name],
    )


async def extract_strategy_review(
    db: AsyncSession,
    user_id: uuid.UUID,
    symbol: str,
    backtest_data: dict[str, Any],
    resource_id: uuid.UUID | None = None,
) -> None:
    """Extract strategy_review memory from a completed backtest result."""
    prediction = backtest_data.get("predicted_direction", "unknown")
    actual = backtest_data.get("actual_direction", "unknown")
    change_pct = backtest_data.get("price_change_pct", 0)
    period = backtest_data.get("period_days", 0)
    direction_correct = backtest_data.get("direction_correct", False)

    verdict = "correct" if direction_correct else "incorrect"
    content = (
        f"Strategy review for {symbol}: "
        f"predicted {prediction}, actual {actual} ({change_pct:+.1f}% over {period} days). "
        f"Direction {verdict}."
    )

    diagnosis = backtest_data.get("diagnosis", {})
    structured = {
        "prediction": prediction,
        "actual": actual,
        "price_change_pct": change_pct,
        "period_days": period,
        "direction_correct": direction_correct,
        "accuracy_verdict": diagnosis.get("accuracy_verdict") if isinstance(diagnosis, dict) else None,
        "root_cause": diagnosis.get("root_cause") if isinstance(diagnosis, dict) else None,
    }

    # Categorize into patterns or mistakes
    category_name = "strategy/patterns" if direction_correct else "strategy/mistakes"

    await create_memory_item(
        db, user_id,
        memory_type="strategy_review",
        content=content,
        structured_data=structured,
        importance_weight=IMPORTANCE_WEIGHTS["strategy_review"],
        happened_at=backtest_data.get("backtest_date"),
        resource_id=resource_id,
        category_names=[f"stock/{symbol}", category_name],
    )


async def ingest_from_run(
    db: AsyncSession,
    user_id: uuid.UUID,
    symbol: str,
    stock_name: str,
    run_result: dict[str, Any],
    run_id: uuid.UUID | None = None,
) -> None:
    """Main entry: extract all memory items from a completed workflow run."""
    from app.db.models import MemoryResource

    # Create resource record
    resource = MemoryResource(
        user_id=user_id,
        source_type="workflow_run",
        source_id=str(run_id) if run_id else None,
        modality="analysis_result",
        snapshot=run_result,
    )
    db.add(resource)
    await db.flush()
    await db.refresh(resource)

    now = datetime.now(timezone.utc)

    # 1. Extract analysis_event
    await extract_analysis_event(
        db, user_id, symbol, run_result,
        happened_at=now, resource_id=resource.id,
    )

    # 2. Extract stock_profile (only if first analysis)
    await extract_stock_profile(
        db, user_id, symbol, stock_name, run_result,
        resource_id=resource.id,
    )
