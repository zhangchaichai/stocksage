"""Evolution schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SuggestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    backtest_id: uuid.UUID | None = None
    evolution_type: str
    target_type: str
    target_name: str
    suggestion_text: str
    suggestion_diff: dict | None = None
    priority: str
    confidence: float
    status: str
    applied_at: datetime | None = None
    created_at: datetime


class SuggestionModifyRequest(BaseModel):
    suggestion_text: str | None = None
    suggestion_diff: dict | None = None
