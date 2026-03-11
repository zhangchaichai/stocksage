"""Pydantic schemas for indicator endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class IndicatorGroup(BaseModel):
    """A group of related indicators (e.g. trend, momentum)."""
    name: str
    label: str
    indicators: dict[str, Any]


class IndicatorResponse(BaseModel):
    """Full indicator response grouped by category."""
    symbol: str
    period: int
    groups: list[IndicatorGroup]
