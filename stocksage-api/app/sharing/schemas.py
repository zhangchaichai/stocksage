from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel


class ShareLinkResponse(BaseModel):
    share_url: str
    workflow_id: uuid.UUID


class WorkflowExport(BaseModel):
    name: str
    description: str
    definition: dict[str, Any]
    version: str
    skills: list[dict[str, Any]] = []


class WorkflowImportResponse(BaseModel):
    workflow_id: uuid.UUID
    name: str
    skills_imported: int
