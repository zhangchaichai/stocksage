"""Pydantic schemas for the chat API."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class ChatMessageRequest(BaseModel):
    """User sends a chat message."""
    message: str


class ChatMessageResponse(BaseModel):
    """Server response with intent recognition."""
    reply: str
    intent: str  # analyze_stock, open_screener, open_indicators, open_backtest, open_portfolio, open_memory, open_evolution, general_question
    action: Optional[str] = None  # navigate, run_analysis, none
    data: Optional[dict[str, Any]] = None  # e.g. {"route": "/screener"}, {"run_id": "..."}


class ChatHistoryItem(BaseModel):
    """A single chat message in history."""
    id: str
    role: str  # user / assistant
    content: str
    intent: Optional[str] = None
    action_data: Optional[dict[str, Any]] = None
    created_at: str
