"""Tests for Portfolio endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def get_auth_header(client: AsyncClient, suffix: str = "") -> dict:
    await client.post(
        "/api/auth/register",
        json={"username": f"testuser{suffix}", "email": f"test{suffix}@test.com", "password": "test123"},
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": f"test{suffix}@test.com", "password": "test123"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_action(client: AsyncClient):
    headers = await get_auth_header(client)
    resp = await client.post(
        "/api/portfolio/actions",
        headers=headers,
        json={
            "symbol": "600519",
            "stock_name": "贵州茅台",
            "action_type": "buy",
            "price": 1800.0,
            "quantity": 100,
            "action_date": "2024-01-15T10:00:00",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["symbol"] == "600519"
    assert data["stock_name"] == "贵州茅台"
    assert data["action_type"] == "buy"
    assert data["price"] == 1800.0
    assert data["quantity"] == 100
    assert "id" in data


@pytest.mark.asyncio
async def test_list_actions(client: AsyncClient):
    headers = await get_auth_header(client)
    await client.post(
        "/api/portfolio/actions",
        headers=headers,
        json={
            "symbol": "600519",
            "action_type": "buy",
            "price": 1800.0,
            "action_date": "2024-01-15T10:00:00",
        },
    )
    resp = await client.get("/api/portfolio/actions", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1


@pytest.mark.asyncio
async def test_get_action(client: AsyncClient):
    headers = await get_auth_header(client)
    create_resp = await client.post(
        "/api/portfolio/actions",
        headers=headers,
        json={
            "symbol": "600519",
            "action_type": "buy",
            "price": 1800.0,
            "action_date": "2024-01-15T10:00:00",
        },
    )
    action_id = create_resp.json()["id"]
    resp = await client.get(f"/api/portfolio/actions/{action_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == action_id


@pytest.mark.asyncio
async def test_update_action(client: AsyncClient):
    headers = await get_auth_header(client)
    create_resp = await client.post(
        "/api/portfolio/actions",
        headers=headers,
        json={
            "symbol": "600519",
            "action_type": "buy",
            "price": 1800.0,
            "action_date": "2024-01-15T10:00:00",
        },
    )
    action_id = create_resp.json()["id"]
    resp = await client.put(
        f"/api/portfolio/actions/{action_id}",
        headers=headers,
        json={"price": 1850.0},
    )
    assert resp.status_code == 200
    assert resp.json()["price"] == 1850.0


@pytest.mark.asyncio
async def test_delete_action(client: AsyncClient):
    headers = await get_auth_header(client)
    create_resp = await client.post(
        "/api/portfolio/actions",
        headers=headers,
        json={
            "symbol": "600519",
            "action_type": "buy",
            "price": 1800.0,
            "action_date": "2024-01-15T10:00:00",
        },
    )
    action_id = create_resp.json()["id"]
    resp = await client.delete(f"/api/portfolio/actions/{action_id}", headers=headers)
    assert resp.status_code == 204
    resp2 = await client.get(f"/api/portfolio/actions/{action_id}", headers=headers)
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_portfolio_summary(client: AsyncClient):
    headers = await get_auth_header(client)
    await client.post(
        "/api/portfolio/actions",
        headers=headers,
        json={
            "symbol": "600519",
            "stock_name": "贵州茅台",
            "action_type": "buy",
            "price": 1800.0,
            "quantity": 100,
            "action_date": "2024-01-15T10:00:00",
        },
    )
    resp = await client.get("/api/portfolio/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["holding_count"] >= 1
    assert "holdings" in data


@pytest.mark.asyncio
async def test_stock_history(client: AsyncClient):
    headers = await get_auth_header(client)
    await client.post(
        "/api/portfolio/actions",
        headers=headers,
        json={
            "symbol": "600519",
            "action_type": "buy",
            "price": 1800.0,
            "action_date": "2024-01-15T10:00:00",
        },
    )
    resp = await client.get("/api/portfolio/600519/history", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["symbol"] == "600519"


@pytest.mark.asyncio
async def test_action_isolation(client: AsyncClient):
    """User A's actions are not visible to User B."""
    headers_a = await get_auth_header(client, suffix="a")
    create_resp = await client.post(
        "/api/portfolio/actions",
        headers=headers_a,
        json={
            "symbol": "600519",
            "action_type": "buy",
            "price": 1800.0,
            "action_date": "2024-01-15T10:00:00",
        },
    )
    action_id = create_resp.json()["id"]

    headers_b = await get_auth_header(client, suffix="b")
    resp = await client.get(f"/api/portfolio/actions/{action_id}", headers=headers_b)
    assert resp.status_code == 404
