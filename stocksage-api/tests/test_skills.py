"""Tests for Skills CRUD endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

_VALID_SKILL_MD = """---
name: test_skill
type: agent
interface:
  inputs:
    - name: data
      source: state.data
  outputs:
    - name: result
      target: state.analysis.test
---

# Test Skill

You are a test analyst.
"""

_INVALID_SKILL_MD = "This is not a valid skill definition"


async def _register(client: AsyncClient, username="skuser", email="sk@example.com") -> str:
    resp = await client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": "secret123"},
    )
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_skill(client: AsyncClient):
    token = await _register(client)
    resp = await client.post(
        "/api/skills",
        json={
            "name": "my_skill",
            "type": "agent",
            "tags": ["test"],
            "definition_md": _VALID_SKILL_MD,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "my_skill"
    assert data["type"] == "agent"


@pytest.mark.asyncio
async def test_create_skill_invalid_md(client: AsyncClient):
    token = await _register(client)
    resp = await client.post(
        "/api/skills",
        json={
            "name": "bad_skill",
            "type": "agent",
            "definition_md": _INVALID_SKILL_MD,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_skills(client: AsyncClient):
    token = await _register(client)
    headers = _auth(token)
    await client.post(
        "/api/skills",
        json={"name": "s1", "type": "agent", "definition_md": _VALID_SKILL_MD},
        headers=headers,
    )
    await client.post(
        "/api/skills",
        json={"name": "s2", "type": "data", "definition_md": _VALID_SKILL_MD},
        headers=headers,
    )

    resp = await client.get("/api/skills", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_get_skill(client: AsyncClient):
    token = await _register(client)
    headers = _auth(token)
    create_resp = await client.post(
        "/api/skills",
        json={"name": "getme", "type": "agent", "definition_md": _VALID_SKILL_MD},
        headers=headers,
    )
    skill_id = create_resp.json()["id"]

    resp = await client.get(f"/api/skills/{skill_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "getme"


@pytest.mark.asyncio
async def test_update_skill(client: AsyncClient):
    token = await _register(client)
    headers = _auth(token)
    create_resp = await client.post(
        "/api/skills",
        json={"name": "old_name", "type": "agent", "definition_md": _VALID_SKILL_MD},
        headers=headers,
    )
    skill_id = create_resp.json()["id"]

    resp = await client.put(
        f"/api/skills/{skill_id}",
        json={"name": "new_name"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "new_name"


@pytest.mark.asyncio
async def test_delete_skill(client: AsyncClient):
    token = await _register(client)
    headers = _auth(token)
    create_resp = await client.post(
        "/api/skills",
        json={"name": "bye", "type": "agent", "definition_md": _VALID_SKILL_MD},
        headers=headers,
    )
    skill_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/skills/{skill_id}", headers=headers)
    assert resp.status_code == 204

    resp2 = await client.get(f"/api/skills/{skill_id}", headers=headers)
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_skill_isolation(client: AsyncClient):
    token_a = await _register(client, "skA", "ska@example.com")
    token_b = await _register(client, "skB", "skb@example.com")

    create_resp = await client.post(
        "/api/skills",
        json={"name": "private_skill", "type": "agent", "definition_md": _VALID_SKILL_MD},
        headers=_auth(token_a),
    )
    skill_id = create_resp.json()["id"]

    resp = await client.get(f"/api/skills/{skill_id}", headers=_auth(token_b))
    assert resp.status_code == 404
