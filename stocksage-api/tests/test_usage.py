"""Tests for Usage endpoints."""

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


@pytest.mark.asyncio
async def test_usage_summary_empty(client: AsyncClient):
    """No usage records returns zeroes."""
    headers = await get_auth_header(client)
    resp = await client.get("/api/usage/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_tokens_input"] == 0
    assert data["total_tokens_output"] == 0
    assert data["total_tokens"] == 0
    assert data["total_runs"] == 0
    assert data["period"] == "all"


@pytest.mark.asyncio
async def test_record_and_get_usage(client: AsyncClient, db_session):
    """Record usage and verify summary reflects it."""
    headers = await get_auth_header(client)

    # Get user id from /me
    me_resp = await client.get("/api/auth/me", headers=headers)
    user_id = uuid.UUID(me_resp.json()["id"])

    # Directly insert usage records via the service
    from app.usage.service import record_usage
    await record_usage(db_session, user_id, None, 100, 50, "deepseek")
    await record_usage(db_session, user_id, None, 200, 100, "deepseek")
    await db_session.commit()

    resp = await client.get("/api/usage/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_tokens_input"] == 300
    assert data["total_tokens_output"] == 150
    assert data["total_tokens"] == 450
    assert data["total_runs"] == 2


@pytest.mark.asyncio
async def test_quota_check(client: AsyncClient):
    """Quota endpoint returns daily limit info."""
    headers = await get_auth_header(client)
    resp = await client.get("/api/usage/quota", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["daily_limit"] == 1000000
    assert data["used_today"] == 0
    assert data["remaining"] == 1000000
