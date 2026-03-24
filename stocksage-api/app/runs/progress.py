"""WebSocket endpoint for real-time run progress with bidirectional control.

Supports:
- Server → Client: progress events (polled from DB)
- Client → Server: commands (pause, resume, question, skip_node)
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.db.models import RunEvent, WorkflowRun
from app.db.session import async_session_factory
from app.runs import control

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/{run_id}/progress")
async def run_progress(websocket: WebSocket, run_id: uuid.UUID):
    """Stream run progress events via WebSocket with bidirectional control.

    Server → Client messages:
        {"event": "node_start", "node": "analyst", "payload": {...}, "timestamp": "..."}
        {"event": "completed", "result": {...}}
        {"event": "paused", "node": "analyst"}
        {"event": "resumed"}

    Client → Server messages:
        {"command": "pause"}
        {"command": "resume"}
        {"command": "skip_node", "node": "analyst"}
    """
    await websocket.accept()
    run_id_str = str(run_id)
    ctrl = control.get_or_create(run_id_str)

    last_event_count = 0

    async def send_events():
        """Poll DB and push new events to client."""
        nonlocal last_event_count

        try:
            while True:
                async with async_session_factory() as db:
                    run_q = select(WorkflowRun).where(WorkflowRun.id == run_id)
                    run_result = await db.execute(run_q)
                    run = run_result.scalar_one_or_none()

                    if run is None:
                        await websocket.send_json({"event": "error", "detail": "Run not found"})
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

                    # Send pause status if changed
                    if ctrl.is_paused:
                        await websocket.send_json({"event": "paused"})

                    # If run is terminal, send final event and stop
                    if run.status in ("completed", "failed", "cancelled"):
                        await websocket.send_json({
                            "event": run.status,
                            "result": run.result,
                            "error": run.error_message,
                        })
                        return

                await asyncio.sleep(0.5)
        except (WebSocketDisconnect, RuntimeError):
            pass

    async def receive_commands():
        """Receive and process commands from client."""
        try:
            while True:
                data = await websocket.receive_json()
                cmd = data.get("command")

                if cmd == "pause":
                    ctrl.pause()
                    await websocket.send_json({"event": "paused"})
                    logger.info("Run %s paused by client", run_id_str)

                elif cmd == "resume":
                    ctrl.resume()
                    await websocket.send_json({"event": "resumed"})
                    logger.info("Run %s resumed by client", run_id_str)

                elif cmd == "skip_node":
                    node = data.get("node", "")
                    await ctrl.command_queue.put({"type": "skip_node", "node": node})
                    logger.info("Run %s: skip_node command for '%s'", run_id_str, node)

                elif cmd == "question":
                    question = data.get("text", "")
                    await ctrl.command_queue.put({"type": "question", "text": question})
                    logger.info("Run %s: question from client", run_id_str)

                else:
                    logger.warning("Run %s: unknown command '%s'", run_id_str, cmd)

        except (WebSocketDisconnect, RuntimeError):
            pass

    try:
        # Run both tasks concurrently; when either finishes, cancel the other
        send_task = asyncio.create_task(send_events())
        recv_task = asyncio.create_task(receive_commands())

        done, pending = await asyncio.wait(
            [send_task, recv_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        control.remove(run_id_str)
        try:
            await websocket.close()
        except Exception:
            pass
