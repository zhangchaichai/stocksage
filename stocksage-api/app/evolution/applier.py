"""Apply evolution suggestions to Skills and Workflows."""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CustomSkill, EvolutionSuggestion, Workflow

logger = logging.getLogger(__name__)


def _bump_version(version: str) -> str:
    """Increment the patch version: 1.0.0 -> 1.0.1"""
    parts = version.split(".")
    if len(parts) == 3:
        parts[2] = str(int(parts[2]) + 1)
        return ".".join(parts)
    return version + ".1"


async def apply_suggestion(
    db: AsyncSession,
    suggestion: EvolutionSuggestion,
    user_id: uuid.UUID,
) -> bool:
    """Apply a suggestion to its target Skill or Workflow. Returns True on success."""
    try:
        if suggestion.evolution_type == "skill_weight":
            return await _apply_skill_weight(db, suggestion, user_id)
        elif suggestion.evolution_type == "skill_prompt":
            return await _apply_skill_prompt(db, suggestion, user_id)
        elif suggestion.evolution_type == "workflow_structure":
            return await _apply_workflow_structure(db, suggestion, user_id)
        elif suggestion.evolution_type == "new_skill":
            return await _apply_new_skill(db, suggestion, user_id)
        else:
            logger.warning("Unknown evolution_type: %s", suggestion.evolution_type)
            return False
    except Exception as e:
        logger.error("Failed to apply suggestion %s: %s", suggestion.id, e)
        return False


async def _find_skill(db: AsyncSession, user_id: uuid.UUID, name: str) -> CustomSkill | None:
    result = await db.execute(
        select(CustomSkill)
        .where(CustomSkill.owner_id == user_id)
        .where(CustomSkill.name == name)
    )
    return result.scalar_one_or_none()


async def _apply_skill_weight(db: AsyncSession, suggestion: EvolutionSuggestion, user_id: uuid.UUID) -> bool:
    """L1: Modify a weight/parameter in a skill definition."""
    skill = await _find_skill(db, user_id, suggestion.target_name)
    if not skill:
        logger.info("Skill %s not found for user, skipping weight change", suggestion.target_name)
        return True  # Not a failure, just no target

    diff = suggestion.suggestion_diff or {}
    field = diff.get("field", "")
    new_value = diff.get("new_value")
    if field and new_value is not None:
        # Append a note about the weight change
        note = f"\n\n<!-- Evolution: {field} adjusted to {new_value} -->\n"
        skill.definition_md += note
        skill.version = _bump_version(skill.version)
        await db.flush()
    return True


async def _apply_skill_prompt(db: AsyncSession, suggestion: EvolutionSuggestion, user_id: uuid.UUID) -> bool:
    """L2: Append or modify a section in a skill's markdown definition."""
    skill = await _find_skill(db, user_id, suggestion.target_name)
    if not skill:
        return True

    diff = suggestion.suggestion_diff or {}
    action = diff.get("action", "append_section")
    title = diff.get("section_title", "Improvement")
    content = diff.get("section_content", suggestion.suggestion_text)

    if action == "append_section":
        skill.definition_md += f"\n\n## {title}\n\n{content}\n"
    elif action == "replace_text":
        old_text = diff.get("old_text", "")
        new_text = diff.get("new_text", content)
        if old_text and old_text in skill.definition_md:
            skill.definition_md = skill.definition_md.replace(old_text, new_text, 1)

    skill.version = _bump_version(skill.version)
    await db.flush()
    return True


async def _apply_workflow_structure(db: AsyncSession, suggestion: EvolutionSuggestion, user_id: uuid.UUID) -> bool:
    """L3: Modify workflow structure (add/remove nodes/edges)."""
    result = await db.execute(
        select(Workflow)
        .where(Workflow.owner_id == user_id)
        .where(Workflow.name == suggestion.target_name)
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        return True

    diff = suggestion.suggestion_diff or {}
    action = diff.get("action", "")
    definition = dict(workflow.definition) if workflow.definition else {"nodes": [], "edges": []}

    if action == "add_node":
        node = diff.get("node")
        if node and isinstance(node, dict):
            definition.setdefault("nodes", []).append(node)
        edges = diff.get("edges", [])
        if edges and isinstance(edges, list):
            definition.setdefault("edges", []).extend(edges)
    elif action == "remove_node":
        node_id = diff.get("node_id", "")
        if node_id:
            definition["nodes"] = [n for n in definition.get("nodes", []) if n.get("id") != node_id]
            definition["edges"] = [e for e in definition.get("edges", [])
                                   if e.get("from") != node_id and e.get("to") != node_id]

    workflow.definition = definition
    workflow.version = _bump_version(workflow.version)
    await db.flush()
    return True


async def _apply_new_skill(db: AsyncSession, suggestion: EvolutionSuggestion, user_id: uuid.UUID) -> bool:
    """L4: Create a new custom skill."""
    # Check if skill already exists
    existing = await _find_skill(db, user_id, suggestion.target_name)
    if existing:
        return True

    new_skill = CustomSkill(
        owner_id=user_id,
        name=suggestion.target_name,
        version="1.0.0",
        type="agent",
        tags=[],
        definition_md=suggestion.suggestion_text,
    )
    db.add(new_skill)
    await db.flush()
    return True
