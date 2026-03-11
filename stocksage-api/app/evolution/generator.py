"""Generate EvolutionSuggestions from BacktestResult diagnosis."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BacktestResult, EvolutionSuggestion

# Map diagnosis suggestion type to evolution fields
_TYPE_MAP = {
    "skill_weight": {"evolution_type": "skill_weight", "target_type": "skill"},
    "skill_prompt": {"evolution_type": "skill_prompt", "target_type": "skill"},
    "workflow_structure": {"evolution_type": "workflow_structure", "target_type": "workflow"},
    "data_source": {"evolution_type": "new_skill", "target_type": "skill"},
    "new_skill": {"evolution_type": "new_skill", "target_type": "skill"},
}

_PRIORITY_MAP = {"high": "high", "medium": "medium", "low": "low"}


async def generate_suggestions(
    db: AsyncSession,
    backtest: BacktestResult,
    user_id: uuid.UUID,
) -> list[EvolutionSuggestion]:
    """Generate evolution suggestions from a backtest result's diagnosis."""
    diagnosis = backtest.diagnosis
    if not diagnosis or not isinstance(diagnosis, dict):
        return []

    suggestions_data = diagnosis.get("improvement_suggestions", [])
    if not isinstance(suggestions_data, list):
        return []

    created = []
    for sug in suggestions_data:
        if not isinstance(sug, dict):
            continue

        sug_type = sug.get("type", "skill_prompt")
        mapping = _TYPE_MAP.get(sug_type, _TYPE_MAP["skill_prompt"])
        priority = _PRIORITY_MAP.get(sug.get("priority", "medium"), "medium")
        target = sug.get("target", "unknown")
        suggestion_text = sug.get("suggestion", "")

        if not suggestion_text:
            continue

        # Build suggestion_diff based on type
        suggestion_diff = None
        if sug_type == "skill_weight":
            suggestion_diff = {
                "field": sug.get("field", ""),
                "old_value": sug.get("old_value"),
                "new_value": sug.get("new_value"),
            }
        elif sug_type == "skill_prompt":
            suggestion_diff = {
                "action": "append_section",
                "section_title": sug.get("section_title", "Improvement"),
                "section_content": suggestion_text,
            }
        elif sug_type == "workflow_structure":
            suggestion_diff = {
                "action": sug.get("action", "add_node"),
                "node": sug.get("node"),
                "edges": sug.get("edges"),
            }

        es = EvolutionSuggestion(
            user_id=user_id,
            backtest_id=backtest.id,
            evolution_type=mapping["evolution_type"],
            target_type=mapping["target_type"],
            target_name=target,
            suggestion_text=suggestion_text,
            suggestion_diff=suggestion_diff,
            priority=priority,
            confidence=sug.get("confidence", 0.5),
            status="pending",
        )
        db.add(es)
        created.append(es)

    if created:
        await db.flush()
        for es in created:
            await db.refresh(es)

    return created
