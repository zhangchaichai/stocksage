"""Sharing router: share links, export, import, public access."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CustomSkill, User, Workflow
from app.db.session import get_db
from app.deps import get_current_user
from app.sharing.schemas import ShareLinkResponse, WorkflowExport, WorkflowImportResponse

router = APIRouter()


@router.post("/workflows/{workflow_id}/share", response_model=ShareLinkResponse)
async def share_workflow(
    workflow_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate share link for a workflow (sets is_public=True)."""
    wf = await db.get(Workflow, workflow_id)
    if wf is None or wf.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Workflow not found")

    wf.is_public = True
    await db.flush()
    await db.refresh(wf)

    base_url = str(request.base_url).rstrip("/")
    share_url = f"{base_url}/api/sharing/public/{wf.id}"

    return ShareLinkResponse(share_url=share_url, workflow_id=wf.id)


@router.get("/workflows/{workflow_id}/export", response_model=WorkflowExport)
async def export_workflow(
    workflow_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export workflow as JSON with embedded skill definitions."""
    wf = await db.get(Workflow, workflow_id)
    if wf is None or (wf.owner_id != current_user.id and not wf.is_public):
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Collect skills referenced in the workflow definition
    skills_data: list[dict] = []
    definition = wf.definition or {}
    nodes = definition.get("nodes", [])
    for node in nodes:
        skill_name = node.get("skill")
        if skill_name:
            result = await db.execute(
                select(CustomSkill).where(
                    CustomSkill.owner_id == wf.owner_id,
                    CustomSkill.name == skill_name,
                )
            )
            skill = result.scalar_one_or_none()
            if skill:
                skills_data.append({
                    "name": skill.name,
                    "type": skill.type,
                    "version": skill.version,
                    "tags": skill.tags or [],
                    "definition_md": skill.definition_md,
                })

    return WorkflowExport(
        name=wf.name,
        description=wf.description or "",
        definition=definition,
        version=wf.version,
        skills=skills_data,
    )


@router.post("/workflows/import", response_model=WorkflowImportResponse)
async def import_workflow(
    body: WorkflowExport,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import workflow from JSON body (creates workflow + skills)."""
    # Create skills first
    skills_imported = 0
    for skill_data in body.skills:
        skill = CustomSkill(
            owner_id=current_user.id,
            name=skill_data.get("name", "imported_skill"),
            version=skill_data.get("version", "1.0.0"),
            type=skill_data.get("type", "agent"),
            tags=skill_data.get("tags", []),
            definition_md=skill_data.get("definition_md", ""),
        )
        db.add(skill)
        skills_imported += 1

    # Create workflow
    wf = Workflow(
        owner_id=current_user.id,
        name=body.name,
        description=body.description,
        definition=body.definition,
        version=body.version,
    )
    db.add(wf)
    await db.flush()
    await db.refresh(wf)

    return WorkflowImportResponse(
        workflow_id=wf.id,
        name=wf.name,
        skills_imported=skills_imported,
    )


@router.get("/public/{workflow_id}")
async def get_public_workflow(
    workflow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a public workflow (no auth required, only if is_public=True)."""
    wf = await db.get(Workflow, workflow_id)
    if wf is None or not wf.is_public:
        raise HTTPException(status_code=404, detail="Public workflow not found")

    return {
        "id": wf.id,
        "name": wf.name,
        "description": wf.description,
        "definition": wf.definition,
        "version": wf.version,
        "is_public": wf.is_public,
        "created_at": wf.created_at.isoformat() if wf.created_at else None,
    }
