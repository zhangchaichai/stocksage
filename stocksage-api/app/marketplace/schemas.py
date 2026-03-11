from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MarketplaceSkillResponse(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    owner_username: str = ""
    name: str
    version: str
    type: str
    tags: list[str] | Any
    definition_md: str
    is_published: bool
    stars_count: int
    starred_by_me: bool = False
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class MarketplaceListResponse(BaseModel):
    items: list[MarketplaceSkillResponse]
    total: int
