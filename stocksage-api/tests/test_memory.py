"""Tests for Memory endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def get_auth_header(client: AsyncClient) -> dict:
    await client.post(
        "/api/auth/register",
        json={"username": "testuser", "email": "test@test.com", "password": "test123"},
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "test@test.com", "password": "test123"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_categories_default(client: AsyncClient):
    """Default categories are auto-seeded for new users."""
    headers = await get_auth_header(client)
    resp = await client.get("/api/memory/categories", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    names = [c["name"] for c in data]
    # Check a few expected default categories
    assert "strategy/patterns" in names
    assert "user/risk_appetite" in names


@pytest.mark.asyncio
async def test_set_and_get_preference(client: AsyncClient):
    """POST a preference, then GET preferences and verify it's present."""
    headers = await get_auth_header(client)

    # Set a preference
    resp = await client.post(
        "/api/memory/preferences",
        json={"key": "risk_tolerance", "value": "medium"},
        headers=headers,
    )
    assert resp.status_code == 200
    created = resp.json()
    assert created["memory_type"] == "user_preference"
    assert created["content"] != ""

    # Get all preferences
    resp2 = await client.get("/api/memory/preferences", headers=headers)
    assert resp2.status_code == 200
    prefs = resp2.json()
    assert len(prefs) >= 1
    assert any(p["id"] == created["id"] for p in prefs)


@pytest.mark.asyncio
async def test_get_stock_memory_empty(client: AsyncClient):
    """GET stock memory for a symbol with no data returns empty structure."""
    headers = await get_auth_header(client)
    resp = await client.get("/api/memory/stock/600519", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "600519"
    assert data["profile"] is None
    assert data["analysis_events"] == []
    assert data["price_anchors"] == []
    assert data["strategy_reviews"] == []
    assert data["actions"] == []


@pytest.mark.asyncio
async def test_stock_timeline_empty(client: AsyncClient):
    """GET stock timeline for a symbol with no data returns empty list."""
    headers = await get_auth_header(client)
    resp = await client.get("/api/memory/stock/600519/timeline", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data == []


@pytest.mark.asyncio
async def test_memory_search_empty(client: AsyncClient):
    """POST /search with a query returns empty list when no data exists."""
    headers = await get_auth_header(client)
    resp = await client.post(
        "/api/memory/search",
        json={"query": "price analysis", "k": 5},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data == []


@pytest.mark.asyncio
async def test_memory_search_no_query(client: AsyncClient):
    """POST /search without a query returns 400."""
    headers = await get_auth_header(client)
    resp = await client.post(
        "/api/memory/search",
        json={},
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_forget_cycle(client: AsyncClient):
    """POST /forget returns dict with compressed and expired_anchors keys."""
    headers = await get_auth_header(client)
    resp = await client.post("/api/memory/forget", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "compressed" in data
    assert "expired_anchors" in data
    assert isinstance(data["compressed"], int)
    assert isinstance(data["expired_anchors"], int)
