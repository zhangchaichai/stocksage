"""Tests for Marketplace endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

_VALID_SKILL_MD = """---
name: marketplace_skill
type: agent
interface:
  inputs:
    - name: data
      source: state.data
  outputs:
    - name: result
      target: state.analysis.test
---

# Marketplace Test Skill

You are a marketplace test analyst.
"""


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


async def _create_and_publish_skill(
    client: AsyncClient, headers: dict, name: str = "pub_skill"
) -> str:
    """Helper: create a skill, publish it, return its id."""
    resp = await client.post(
        "/api/skills",
        json={
            "name": name,
            "type": "agent",
            "tags": ["test", "marketplace"],
            "definition_md": _VALID_SKILL_MD,
        },
        headers=headers,
    )
    skill_id = resp.json()["id"]
    await client.post(f"/api/marketplace/skills/{skill_id}/publish", headers=headers)
    return skill_id


@pytest.mark.asyncio
async def test_list_marketplace_empty(client: AsyncClient):
    """No published skills returns empty list."""
    resp = await client.get("/api/marketplace/skills")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_publish_skill(client: AsyncClient):
    """Create a skill, publish it, check it appears in marketplace."""
    headers = await get_auth_header(client)

    # Create skill
    resp = await client.post(
        "/api/skills",
        json={
            "name": "to_publish",
            "type": "agent",
            "tags": ["test"],
            "definition_md": _VALID_SKILL_MD,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    skill_id = resp.json()["id"]

    # Publish
    resp = await client.post(f"/api/marketplace/skills/{skill_id}/publish", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_published"] is True

    # Check marketplace listing
    resp = await client.get("/api/marketplace/skills")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "to_publish"
    assert data["items"][0]["is_published"] is True


@pytest.mark.asyncio
async def test_star_skill(client: AsyncClient):
    """Publish, star, and check stars_count increments."""
    headers = await get_auth_header(client)
    skill_id = await _create_and_publish_skill(client, headers, "starrable")

    # Star
    resp = await client.post(f"/api/marketplace/skills/{skill_id}/star", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["starred"] is True
    assert resp.json()["stars_count"] == 1


@pytest.mark.asyncio
async def test_unstar_skill(client: AsyncClient):
    """Star then star again to unstar."""
    headers = await get_auth_header(client)
    skill_id = await _create_and_publish_skill(client, headers, "toggle_star")

    # Star
    resp = await client.post(f"/api/marketplace/skills/{skill_id}/star", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["starred"] is True

    # Unstar (toggle)
    resp = await client.post(f"/api/marketplace/skills/{skill_id}/star", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["starred"] is False
    assert resp.json()["stars_count"] == 0


@pytest.mark.asyncio
async def test_fork_skill(client: AsyncClient):
    """Fork a published skill."""
    headers = await get_auth_header(client)
    skill_id = await _create_and_publish_skill(client, headers, "forkable")

    # Fork
    resp = await client.post(f"/api/marketplace/skills/{skill_id}/fork", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["forked_from"] == skill_id
    assert "fork" in data["name"].lower()


@pytest.mark.asyncio
async def test_marketplace_search(client: AsyncClient):
    """Search by name in marketplace."""
    headers = await get_auth_header(client)
    await _create_and_publish_skill(client, headers, "alpha_analyzer")
    await _create_and_publish_skill(client, headers, "beta_predictor")

    # Search for "alpha"
    resp = await client.get("/api/marketplace/skills?search=alpha")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "alpha_analyzer"

    # Search for "predictor"
    resp = await client.get("/api/marketplace/skills?search=predictor")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "beta_predictor"
