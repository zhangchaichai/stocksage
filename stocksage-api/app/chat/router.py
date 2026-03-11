"""Chat API router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatMessage, User
from app.db.session import get_db
from app.deps import get_current_user
from app.chat.intent import recognize_intent_with_llm
from app.chat.schemas import ChatHistoryItem, ChatMessageRequest, ChatMessageResponse
from app.chat.service import handle_intent

router = APIRouter()


@router.post("/message", response_model=ChatMessageResponse)
async def send_message(
    body: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a chat message and get an intent-aware response."""
    # Save user message
    user_msg = ChatMessage(
        user_id=current_user.id,
        role="user",
        content=body.message,
    )
    db.add(user_msg)
    await db.flush()

    # Recognize intent
    intent, metadata = await recognize_intent_with_llm(body.message)

    # Handle intent
    response = await handle_intent(intent, metadata, body.message, current_user.id, db)

    # Save assistant response
    assistant_msg = ChatMessage(
        user_id=current_user.id,
        role="assistant",
        content=response.reply,
        intent=response.intent,
        action_data={"action": response.action, "data": response.data} if response.action else None,
    )
    db.add(assistant_msg)
    await db.flush()

    return response


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
        for m in reversed(messages)  # Return in chronological order
    ]
