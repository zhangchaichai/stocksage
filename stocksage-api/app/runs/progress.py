"""WebSocket endpoint for real-time run progress."""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RunEvent, WorkflowRun
from app.db.session import async_session_factory

router = APIRouter()


@router.websocket("/{run_id}/progress")
async def run_progress(websocket: WebSocket, run_id: uuid.UUID):
    """Stream run progress events via WebSocket.

    The client connects and receives JSON events as they are recorded.
    For now, this polls the run_events table. In production, this would
    subscribe to Redis pub/sub for real-time delivery.
    """
    await websocket.accept()

    last_event_count = 0

    try:
        while True:
            async with async_session_factory() as db:
                # Check if run exists
                run_q = select(WorkflowRun).where(WorkflowRun.id == run_id)
                run_result = await db.execute(run_q)
                run = run_result.scalar_one_or_none()

                if run is None:
                    await websocket.send_json({"event": "error", "detail": "Run not found"})
                    await websocket.close()
                    return

                # Fetch new events since last check
                events_q = (
                    select(RunEvent)
                    .where(RunEvent.run_id == run_id)
                    .order_by(RunEvent.created_at)
                )
                events_result = await db.execute(events_q)
                events = list(events_result.scalars().all())

                # Send only new events
                for event in events[last_event_count:]:
                    await websocket.send_json({
                        "event": event.event_type,
                        "node": event.node_name,
                        "phase": event.phase,
                        "payload": event.payload or {},
                        "timestamp": event.created_at.isoformat() if event.created_at else None,
                    })
                last_event_count = len(events)

                # If run is terminal, send final event and close
                if run.status in ("completed", "failed", "cancelled"):
                    await websocket.send_json({
                        "event": run.status,
                        "result": run.result,
                        "error": run.error_message,
                    })
                    await websocket.close()
                    return

            # Poll interval
            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        pass
