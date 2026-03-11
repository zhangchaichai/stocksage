"""Tests for Backtest and Evolution endpoints."""

from __future__ import annotations

import uuid

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


# ---- Backtest ----


@pytest.mark.asyncio
async def test_backtest_results_empty(client: AsyncClient):
    """No backtest results returns empty list."""
    headers = await get_auth_header(client)
    resp = await client.get("/api/backtest/results", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_backtest_stats_empty(client: AsyncClient):
    """No backtest data returns zeroed stats."""
    headers = await get_auth_header(client)
    resp = await client.get("/api/backtest/stats", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_actions"] == 0
    assert data["direction_accuracy"] == 0.0
    assert data["avg_return"] == 0.0
    assert data["win_rate"] == 0.0
    assert data["max_drawdown"] == 0.0


@pytest.mark.asyncio
async def test_backtest_symbol_stats_empty(client: AsyncClient):
    """Symbol-specific stats returns zeroes when no data exists."""
    headers = await get_auth_header(client)
    resp = await client.get("/api/backtest/stats/600519", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_actions"] == 0
    assert data["direction_accuracy"] == 0.0
    assert data["avg_return"] == 0.0
    assert data["win_rate"] == 0.0
    assert data["max_drawdown"] == 0.0


@pytest.mark.asyncio
async def test_backtest_result_not_found(client: AsyncClient):
    """Getting a non-existent backtest result returns 404."""
    headers = await get_auth_header(client)
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/backtest/results/{fake_id}", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_backtest_run_all_empty(client: AsyncClient):
    """Batch backtest with no actions returns empty list."""
    headers = await get_auth_header(client)
    resp = await client.post(
        "/api/backtest/run-all",
        json={"period_days": 30},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json() == []


# ---- Evolution ----


@pytest.mark.asyncio
async def test_evolution_suggestions_empty(client: AsyncClient):
    """No evolution suggestions returns empty list."""
    headers = await get_auth_header(client)
    resp = await client.get("/api/evolution/suggestions", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_evolution_history_empty(client: AsyncClient):
    """No evolution history returns empty list."""
    headers = await get_auth_header(client)
    resp = await client.get("/api/evolution/history", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_evolution_accept_not_found(client: AsyncClient):
    """Accepting a non-existent suggestion returns 404."""
    headers = await get_auth_header(client)
    fake_id = str(uuid.uuid4())
    resp = await client.post(
        f"/api/evolution/suggestions/{fake_id}/accept", headers=headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_evolution_reject_not_found(client: AsyncClient):
    """Rejecting a non-existent suggestion returns 404."""
    headers = await get_auth_header(client)
    fake_id = str(uuid.uuid4())
    resp = await client.post(
        f"/api/evolution/suggestions/{fake_id}/reject", headers=headers
    )
    assert resp.status_code == 404
