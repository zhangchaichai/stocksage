"""Workflow Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    definition: dict[str, Any]
    version: str = "1.0.0"
    is_public: bool = False


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    definition: dict[str, Any] | None = None
    version: str | None = None
    is_public: bool | None = None


class WorkflowResponse(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str
    definition: dict[str, Any]
    version: str
    is_public: bool
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class WorkflowListResponse(BaseModel):
    items: list[WorkflowResponse]
    total: int


class WorkflowValidationError(BaseModel):
    errors: list[str]


class WorkflowTemplate(BaseModel):
    name: str
    description: str
    definition: dict[str, Any]
