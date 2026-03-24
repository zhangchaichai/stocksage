"""Chat API router.

Provides both the legacy synchronous endpoint (/message) and the new
SSE streaming endpoint (/stream) powered by ChatAgent.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatMessage, User
from app.db.session import get_db
from app.deps import get_current_user
from app.chat.schemas import ChatHistoryItem, ChatMessageRequest, ChatMessageResponse

logger = logging.getLogger(__name__)
router = APIRouter()


# ── helpers ──────────────────────────────────────────────────

async def _load_recent_history(
    user_id: int,
    db: AsyncSession,
    limit: int = 20,
) -> list[dict[str, str]]:
    """从 DB 加载最近的对话历史，转换为 LLM messages 格式。"""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    messages = list(reversed(result.scalars().all()))
    return [{"role": m.role, "content": m.content} for m in messages]


async def _ensure_builtin_workflow(db, workflow_name: str, owner_id):
    """Auto-seed a built-in workflow from YAML into the DB if not present."""
    from pathlib import Path

    from app.workflows.service import create_workflow

    try:
        import stocksage
        workflows_dir = Path(stocksage.__file__).parent / "workflows"
        for suffix in (".yaml", ".yml"):
            yaml_path = workflows_dir / f"{workflow_name}{suffix}"
            if yaml_path.exists():
                import yaml
                with open(yaml_path) as f:
                    definition = yaml.safe_load(f)
                wf = await create_workflow(
                    db,
                    owner_id=owner_id,
                    name=workflow_name,
                    description=f"Built-in {workflow_name} workflow (auto-seeded)",
                    definition=definition,
                    is_public=True,
                )
                logger.info("Auto-seeded workflow '%s' into DB", workflow_name)
                return wf
    except Exception as e:
        logger.warning("Failed to auto-seed workflow '%s': %s", workflow_name, e)
    return None


def _get_chat_agent(current_user_id=None):
    """Lazy-construct a ChatAgent with its tool registry."""
    from uuid import UUID

    from app.chat.agent import ChatAgent
    from app.chat.chat_tools import build_chat_tool_registry
    from stocksage.agent.llm_adapter import LiteLLMAdapter

    # Construct DataFetcher for query_stock tool
    fetcher = None
    try:
        from stocksage.data.fetcher import DataFetcher
        fetcher = DataFetcher()
    except Exception:
        pass

    # Build create_run_fn closure that captures user context
    create_run_fn = None
    if current_user_id is not None:
        async def create_run_fn(symbol: str, stock_name: str, mode: str):
            """Create and start a workflow run for the given stock."""
            from sqlalchemy import select as sa_select

            from app.config import settings as app_settings
            from app.db.models import Workflow
            from app.db.session import async_session_factory
            from app.runs.service import create_run

            # Map chat mode to built-in workflow name
            workflow_map = {
                "quick": "quick_analysis",
                "standard": "full_spectrum",
                "deep": "deep_fundamental",
            }
            workflow_name = workflow_map.get(mode, "quick_analysis")

            try:
                async with async_session_factory() as db:
                    # Find a matching workflow (user-owned or public)
                    result = await db.execute(
                        sa_select(Workflow)
                        .where(
                            (Workflow.name == workflow_name)
                            & (
                                (Workflow.owner_id == current_user_id)
                                | (Workflow.is_public.is_(True))
                            )
                        )
                        .limit(1)
                    )
                    wf = result.scalar_one_or_none()

                    # Fallback: try any available workflow
                    if wf is None:
                        result = await db.execute(
                            sa_select(Workflow)
                            .where(
                                (Workflow.owner_id == current_user_id)
                                | (Workflow.is_public.is_(True))
                            )
                            .limit(1)
                        )
                        wf = result.scalar_one_or_none()

                    # Auto-seed from built-in YAML if no DB workflow exists
                    if wf is None:
                        wf = await _ensure_builtin_workflow(
                            db, workflow_name, current_user_id,
                        )

                    if wf is None:
                        logger.warning("No workflow found for mode=%s", mode)
                        return None

                    run = await create_run(
                        db,
                        owner_id=current_user_id,
                        workflow_id=wf.id,
                        symbol=symbol,
                        stock_name=stock_name,
                    )
                    await db.commit()
                    await db.refresh(run)

                    # Dispatch execution
                    if app_settings.USE_ORCHESTRATOR:
                        from app.runs.orchestrator import get_orchestrator
                        orchestrator = get_orchestrator()
                        await orchestrator.start_run(
                            run_id=run.id,
                            workflow_name=wf.name,
                            workflow_definition=wf.definition,
                            symbol=symbol,
                            stock_name=stock_name,
                            owner_id=current_user_id,
                        )
                    else:
                        from app.runs.worker import dispatch_run
                        dispatch_run(run.id)

                    return str(run.id)
            except Exception as e:
                logger.error("Failed to create analysis run: %s", e)
                return None

    tool_registry = build_chat_tool_registry(
        fetcher=fetcher,
        create_run_fn=create_run_fn,
    )

    # LiteLLMAdapter auto-resolves API key from environment / .env
    # Use app config to determine provider/model
    from app.config import settings
    provider = settings.DEFAULT_LLM_PROVIDER or "deepseek"
    model = f"{provider}-chat" if provider == "deepseek" else provider
    llm = LiteLLMAdapter(model=model)
    return ChatAgent(llm=llm, tool_registry=tool_registry)


# ── SSE streaming endpoint (new) ────────────────────────────

@router.post("/stream")
async def chat_stream(
    body: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """流式对话端点 — SSE 格式。

    返回 SSE 流:
      event: thinking    data: {"content": "..."}
      event: tool_call   data: {"tool": "...", ...}
      event: tool_result data: {"tool": "...", ...}
      event: action      data: {"action": "navigate", ...}
      event: token       data: {"content": "..."}
      event: done        data: {"full_reply": "...", "actions": [...]}
    """
    # Save user message
    user_msg = ChatMessage(
        user_id=current_user.id,
        role="user",
        content=body.message,
    )
    db.add(user_msg)
    await db.flush()

    # Load history
    history = await _load_recent_history(current_user.id, db, limit=20)

    # Build agent
    agent = _get_chat_agent(current_user_id=current_user.id)

    async def event_generator():
        full_reply = ""
        try:
            async for event in agent.chat_stream(body.message, history):
                if event.get("type") == "done":
                    full_reply = event.get("full_reply", "")
                event_type = event.get("type", "message")
                payload = {k: v for k, v in event.items() if k != "type"}
                data = json.dumps(payload, ensure_ascii=False)
                yield f"event: {event_type}\ndata: {data}\n\n"
        except Exception as e:
            logger.error("Chat stream error: %s", e)
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

        # Save assistant reply
        if full_reply:
            assistant_msg = ChatMessage(
                user_id=current_user.id,
                role="assistant",
                content=full_reply,
                intent="agent",
            )
            db.add(assistant_msg)
            await db.flush()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Legacy synchronous endpoint (preserved) ─────────────────

@router.post("/message", response_model=ChatMessageResponse)
async def send_message(
    body: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a chat message — backward-compatible non-streaming endpoint.

    Internally delegates to ChatAgent but collects the full response
    before returning.
    """
    # Save user message
    user_msg = ChatMessage(
        user_id=current_user.id,
        role="user",
        content=body.message,
    )
    db.add(user_msg)
    await db.flush()

    # Load history and run agent
    history = await _load_recent_history(current_user.id, db, limit=20)
    agent = _get_chat_agent(current_user_id=current_user.id)

    full_reply = ""
    actions: list[dict] = []
    try:
        async for event in agent.chat_stream(body.message, history):
            if event.get("type") == "done":
                full_reply = event.get("full_reply", "")
                actions = event.get("actions", [])
    except Exception as e:
        logger.error("ChatAgent execution failed: %s", e)
        full_reply = "抱歉，服务暂时不可用，请稍后再试。"

    if not full_reply:
        full_reply = "抱歉，未能生成回复，请稍后再试。"

    # Extract first action
    first_action = actions[0] if actions else None

    # Save assistant response
    assistant_msg = ChatMessage(
        user_id=current_user.id,
        role="assistant",
        content=full_reply,
        intent="agent",
        action_data=(
            {"action": first_action["action"], "data": first_action.get("data")}
            if first_action
            else None
        ),
    )
    db.add(assistant_msg)
    await db.flush()

    return ChatMessageResponse(
        reply=full_reply,
        intent="agent",
        action=first_action["action"] if first_action else "none",
        data=first_action.get("data") if first_action else None,
    )


# ── History endpoint (unchanged) ─────────────────────────────

@router.get("/history", response_model=list[ChatHistoryItem])
async def get_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get recent chat history for the current user."""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    messages = result.scalars().all()

    return [
        ChatHistoryItem(
            id=str(m.id),
            role=m.role,
            content=m.content,
            intent=m.intent,
            action_data=m.action_data,
            created_at=m.created_at.isoformat() if m.created_at else "",
        )
        for m in reversed(messages)
    ]
