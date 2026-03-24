"""Runs router: submit, list, get, cancel, batch, SSE stream."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import User
from app.db.session import get_db
from app.deps import get_current_user
from app.runs.schemas import BatchRunCreate, InteractionResponse, RunCreate, RunListResponse, RunResponse
from app.runs.service import create_run, get_run, list_runs, update_run_status

router = APIRouter()


def _get_dispatch():
    """根据配置选择 dispatch 方式。"""
    if settings.USE_ORCHESTRATOR:
        from app.runs.orchestrator import RunOrchestrator
        return "orchestrator"
    else:
        from app.runs.worker import dispatch_run
        return "worker"


@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def submit_run(
    body: RunCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.workflows.service import get_workflow

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
    if settings.USE_ORCHESTRATOR:
        from app.runs.orchestrator import get_orchestrator
        orchestrator = get_orchestrator()
        await orchestrator.start_run(
            run_id=run.id,
            workflow_name=wf.name,
            workflow_definition=wf.definition,
            symbol=body.symbol,
            stock_name=body.stock_name,
            owner_id=current_user.id,
        )
    else:
        from app.runs.worker import dispatch_run
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


@router.get("/{run_id}/stream")
async def stream_run_events(
    run_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE endpoint: 流式推送分析进展。

    支持断线重连: Producer 独立于 Consumer，事件持久化到 DB。
    客户端重连后自动回放历史事件。
    """
    run = await get_run(db, run_id)
    if run is None or run.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")

    from app.runs.orchestrator import get_orchestrator
    orchestrator = get_orchestrator()

    async def generate():
        async for event in orchestrator.stream_events(run_id):
            event_type = event.get("event", "message")
            # Build SSE data payload (exclude 'event' key from data)
            data = {k: v for k, v in event.items() if k != "event"}
            yield f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/{run_id}/respond")
async def respond_to_interaction(
    run_id: uuid.UUID,
    body: InteractionResponse,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """投递用户响应到等待中的交互节点。

    当工作流中的 interaction 节点暂停等待用户输入时，
    前端调用此接口投递用户的选择/输入。
    """
    run = await get_run(db, run_id)
    if run is None or run.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")

    from app.runs.orchestrator import get_orchestrator
    orchestrator = get_orchestrator()

    delivered = await orchestrator.respond_to_interaction(run_id, body.response)
    if not delivered:
        raise HTTPException(
            status_code=404,
            detail="No pending interaction for this run",
        )

    return {"status": "ok", "run_id": str(run_id)}


@router.post("/batch", response_model=list[RunResponse], status_code=status.HTTP_201_CREATED)
async def batch_submit_runs(
    body: BatchRunCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit multiple workflow runs in one request (from screener results)."""
    from app.workflows.service import get_workflow

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
        if settings.USE_ORCHESTRATOR:
            from app.runs.orchestrator import get_orchestrator
            orchestrator = get_orchestrator()
            await orchestrator.start_run(
                run_id=run.id,
                workflow_name=wf.name,
                workflow_definition=wf.definition,
                symbol=run.symbol,
                stock_name=run.stock_name,
                owner_id=current_user.id,
            )
        else:
            from app.runs.worker import dispatch_run
            dispatch_run(run.id)

    return runs
