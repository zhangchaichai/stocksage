"""Evolution API router."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db
from app.db.models import User
from app.evolution import schemas, service

router = APIRouter()


@router.get("/suggestions", response_model=list[schemas.SuggestionResponse])
async def list_suggestions(
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items, total = await service.list_suggestions(db, user.id, status, skip, limit)
    return items


@router.get("/suggestions/{suggestion_id}", response_model=schemas.SuggestionResponse)
async def get_suggestion(
    suggestion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sug = await service.get_suggestion(db, suggestion_id)
    if sug is None or sug.user_id != user.id:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return sug


@router.post("/suggestions/{suggestion_id}/accept", response_model=schemas.SuggestionResponse)
async def accept_suggestion(
    suggestion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sug = await service.get_suggestion(db, suggestion_id)
    if sug is None or sug.user_id != user.id:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    if sug.status != "pending":
        raise HTTPException(status_code=400, detail="Suggestion is not pending")
    await service.accept_suggestion(db, sug, user.id)
    await db.commit()
    return sug


@router.post("/suggestions/{suggestion_id}/reject", response_model=schemas.SuggestionResponse)
async def reject_suggestion(
    suggestion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sug = await service.get_suggestion(db, suggestion_id)
    if sug is None or sug.user_id != user.id:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    if sug.status != "pending":
        raise HTTPException(status_code=400, detail="Suggestion is not pending")
    await service.reject_suggestion(db, sug)
    await db.commit()
    return sug


@router.put("/suggestions/{suggestion_id}/modify", response_model=schemas.SuggestionResponse)
async def modify_and_accept(
    suggestion_id: uuid.UUID,
    body: schemas.SuggestionModifyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sug = await service.get_suggestion(db, suggestion_id)
    if sug is None or sug.user_id != user.id:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    if sug.status != "pending":
        raise HTTPException(status_code=400, detail="Suggestion is not pending")
    await service.modify_and_accept(db, sug, user.id, body.model_dump(exclude_none=True))
    await db.commit()
    return sug


@router.get("/history", response_model=list[schemas.SuggestionResponse])
async def get_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items, total = await service.get_history(db, user.id, skip, limit)
    return items
