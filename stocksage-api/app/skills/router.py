"""Skills router: CRUD for custom skills + built-in skill catalog."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_db
from app.deps import get_current_user
from app.skills.schemas import (
    BuiltinSkillResponse,
    SkillCreate,
    SkillListResponse,
    SkillResponse,
    SkillUpdate,
)
from app.skills.service import (
    create_skill,
    delete_skill,
    get_skill,
    list_skills,
    update_skill,
)

router = APIRouter()

# ---- Built-in skills catalog ----

# Path to the core engine's skills directory
_SKILLS_DIR = Path(__file__).resolve().parents[3] / "stocksage" / "skills"

_CATEGORY_MAP = {
    "data": "Data",
    "agents": "Analyst",
    "debate": "Debate",
    "experts": "Expert",
    "decision": "Decision",
    "researcher": "Expert",
}


def _load_builtin_skills() -> list[dict]:
    """Scan the stocksage/skills directory and load all .md skill files."""
    skills: list[dict] = []
    if not _SKILLS_DIR.is_dir():
        return skills
    for subdir in sorted(_SKILLS_DIR.iterdir()):
        if not subdir.is_dir():
            continue
        category = _CATEGORY_MAP.get(subdir.name, subdir.name.capitalize())
        for md_file in sorted(subdir.glob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            # Parse YAML front-matter
            name = md_file.stem
            skill_type = subdir.name
            version = "1.0.0"
            description = ""
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    front_matter = parts[1]
                    for line in front_matter.strip().splitlines():
                        line = line.strip()
                        if line.startswith("name:"):
                            name = line.split(":", 1)[1].strip().strip('"').strip("'")
                        elif line.startswith("type:"):
                            skill_type = line.split(":", 1)[1].strip().strip('"').strip("'")
                        elif line.startswith("version:"):
                            version = line.split(":", 1)[1].strip().strip('"').strip("'")
                        elif line.startswith("description:"):
                            description = line.split(":", 1)[1].strip().strip('"').strip("'")
            skills.append({
                "name": name,
                "type": skill_type,
                "category": category,
                "version": version,
                "description": description,
                "definition_md": content,
            })
    return skills


# Cache built-in skills at import time
_BUILTIN_SKILLS: list[dict] = _load_builtin_skills()


def _validate_skill_md(md: str) -> list[str]:
    """Basic validation: skill .md must have YAML front-matter."""
    errors: list[str] = []
    stripped = md.strip()
    if not stripped.startswith("---"):
        errors.append("Skill definition must start with YAML front-matter (---)")
    elif stripped.count("---") < 2:
        errors.append("Skill definition must have closing YAML front-matter (---)")
    return errors


@router.get("", response_model=SkillListResponse)
async def list_my_skills(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await list_skills(db, current_user.id, skip, limit)
    return SkillListResponse(items=items, total=total)


@router.get("/builtins", response_model=list[BuiltinSkillResponse])
async def list_builtin_skills():
    """Return the catalog of built-in skills from the core engine."""
    return _BUILTIN_SKILLS


@router.post("", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
async def create_new_skill(
    body: SkillCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    validation_errors = _validate_skill_md(body.definition_md)
    if validation_errors:
        raise HTTPException(status_code=422, detail=validation_errors)
    skill = await create_skill(
        db, current_user.id, body.name, body.version,
        body.type, body.tags, body.definition_md,
    )
    return skill


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill_detail(
    skill_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    skill = await get_skill(db, skill_id)
    if skill is None or skill.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_existing_skill(
    skill_id: uuid.UUID,
    body: SkillUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    skill = await get_skill(db, skill_id)
    if skill is None or skill.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Skill not found")
    updates = body.model_dump(exclude_unset=True)
    if "definition_md" in updates and updates["definition_md"] is not None:
        validation_errors = _validate_skill_md(updates["definition_md"])
        if validation_errors:
            raise HTTPException(status_code=422, detail=validation_errors)
    skill = await update_skill(db, skill, updates)
    return skill


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_skill(
    skill_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    skill = await get_skill(db, skill_id)
    if skill is None or skill.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Skill not found")
    await delete_skill(db, skill)
