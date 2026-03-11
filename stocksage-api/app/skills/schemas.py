"""Skill Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    version: str = "1.0.0"
    type: str = Field(min_length=1, max_length=32)  # agent, data, decision, etc.
    tags: list[str] = []
    definition_md: str = Field(min_length=1)


class SkillUpdate(BaseModel):
    name: str | None = None
    version: str | None = None
    type: str | None = None
    tags: list[str] | None = None
    definition_md: str | None = None


class SkillResponse(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    version: str
    type: str
    tags: list[str] | Any
    definition_md: str
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class SkillListResponse(BaseModel):
    items: list[SkillResponse]
    total: int


class BuiltinSkillResponse(BaseModel):
    name: str
    type: str
    category: str
    version: str
    description: str
    definition_md: str
