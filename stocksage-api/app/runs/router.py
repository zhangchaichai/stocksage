"""Runs router: submit, list, get, cancel, batch."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_db
from app.deps import get_current_user
from app.runs.schemas import BatchRunCreate, RunCreate, RunListResponse, RunResponse
from app.runs.service import create_run, get_run, list_runs, update_run_status
from app.runs.worker import dispatch_run
from app.workflows.service import get_workflow

router = APIRouter()


@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def submit_run(
    body: RunCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wf = await get_workflow(db, body.workflow_id)
    if wf is None or (wf.owner_id != current_user.id and not wf.is_public):
        raise HTTPException(status_code=404, detail="Workflow not found")

    run = await create_run(
        db, current_user.id, body.workflow_id,
        body.symbol, body.stock_name, body.config_overrides,
    )
    # Commit so worker can read the run from a separate session
    await db.commit()
    await db.refresh(run)

    # Dispatch background execution
    dispatch_run(run.id)

    return run


@router.get("", response_model=RunListResponse)
async def list_my_runs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await list_runs(db, current_user.id, skip, limit)
    return RunListResponse(items=items, total=total)


@router.get("/{run_id}", response_model=RunResponse)
async def get_run_detail(
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await get_run(db, run_id)
    if run is None or run.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_run(
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await get_run(db, run_id)
    if run is None or run.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status not in ("queued", "running"):
        raise HTTPException(status_code=409, detail="Run cannot be cancelled in current state")
    await update_run_status(db, run, "cancelled")


@router.post("/batch", response_model=list[RunResponse], status_code=status.HTTP_201_CREATED)
async def batch_submit_runs(
    body: BatchRunCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit multiple workflow runs in one request (from screener results).

    All runs share the same workflow and config_overrides.  Each symbol in
    ``body.symbols`` becomes an independent WorkflowRun queued for execution.

    ``body.source`` is stored in ``config_overrides._source`` for traceability
    (e.g. ``"screener_job:abc123"``).
    """
    wf = await get_workflow(db, body.workflow_id)
    if wf is None or (wf.owner_id != current_user.id and not wf.is_public):
        raise HTTPException(status_code=404, detail="Workflow not found")

    if len(body.symbols) > 50:
        raise HTTPException(status_code=400, detail="Cannot submit more than 50 runs at once")

    stock_names = body.stock_names or {}
    overrides = dict(body.config_overrides)
    if body.source:
        overrides["_source"] = body.source

    runs = []
    for symbol in body.symbols:
        name = stock_names.get(symbol, "")
        run = await create_run(
            db,
            owner_id=current_user.id,
            workflow_id=body.workflow_id,
            symbol=symbol.upper(),
            stock_name=name,
            config_overrides=overrides,
        )
        runs.append(run)

    await db.commit()
    for run in runs:
        await db.refresh(run)
        dispatch_run(run.id)

    return runs
