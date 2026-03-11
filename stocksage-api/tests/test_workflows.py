"""Tests for Workflow CRUD endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

_VALID_DEFINITION = {
    "name": "test_workflow",
    "nodes": [
        {"id": "collect_data", "skill": "data_collector"},
        {"id": "analyst", "skill": "technical_analyst"},
    ],
    "edges": [
        {"from": "START", "to": "collect_data"},
        {"from": "collect_data", "to": "analyst"},
        {"from": "analyst", "to": "END"},
    ],
}


async def _register(client: AsyncClient, username="wfuser", email="wf@example.com") -> str:
    resp = await client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": "secret123"},
    )
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_workflow(client: AsyncClient):
    token = await _register(client)
    resp = await client.post(
        "/api/workflows",
        json={"name": "My Flow", "definition": _VALID_DEFINITION},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Flow"
    assert data["definition"]["name"] == "test_workflow"


@pytest.mark.asyncio
async def test_list_workflows(client: AsyncClient):
    token = await _register(client)
    headers = _auth(token)
    await client.post("/api/workflows", json={"name": "WF1", "definition": _VALID_DEFINITION}, headers=headers)
    await client.post("/api/workflows", json={"name": "WF2", "definition": _VALID_DEFINITION}, headers=headers)

    resp = await client.get("/api/workflows", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_get_workflow(client: AsyncClient):
    token = await _register(client)
    headers = _auth(token)
    create_resp = await client.post(
        "/api/workflows", json={"name": "GetMe", "definition": _VALID_DEFINITION}, headers=headers,
    )
    wf_id = create_resp.json()["id"]

    resp = await client.get(f"/api/workflows/{wf_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "GetMe"


@pytest.mark.asyncio
async def test_update_workflow(client: AsyncClient):
    token = await _register(client)
    headers = _auth(token)
    create_resp = await client.post(
        "/api/workflows", json={"name": "Old", "definition": _VALID_DEFINITION}, headers=headers,
    )
    wf_id = create_resp.json()["id"]

    resp = await client.put(
        f"/api/workflows/{wf_id}", json={"name": "New"}, headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"


@pytest.mark.asyncio
async def test_delete_workflow(client: AsyncClient):
    token = await _register(client)
    headers = _auth(token)
    create_resp = await client.post(
        "/api/workflows", json={"name": "Bye", "definition": _VALID_DEFINITION}, headers=headers,
    )
    wf_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/workflows/{wf_id}", headers=headers)
    assert resp.status_code == 204

    resp2 = await client.get(f"/api/workflows/{wf_id}", headers=headers)
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_workflow_isolation(client: AsyncClient):
    """User A cannot access User B's workflow."""
    token_a = await _register(client, "userA", "a@example.com")
    token_b = await _register(client, "userB", "b@example.com")

    create_resp = await client.post(
        "/api/workflows",
        json={"name": "Private", "definition": _VALID_DEFINITION},
        headers=_auth(token_a),
    )
    wf_id = create_resp.json()["id"]

    resp = await client.get(f"/api/workflows/{wf_id}", headers=_auth(token_b))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_validate_valid(client: AsyncClient):
    resp = await client.post(
        "/api/workflows/validate",
        json={"name": "V", "definition": _VALID_DEFINITION},
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


@pytest.mark.asyncio
async def test_validate_invalid_orphan(client: AsyncClient):
    bad_def = {
        "nodes": [
            {"id": "a", "skill": "x"},
            {"id": "orphan", "skill": "y"},
        ],
        "edges": [
            {"from": "START", "to": "a"},
            {"from": "a", "to": "END"},
        ],
    }
    resp = await client.post(
        "/api/workflows/validate",
        json={"name": "Bad", "definition": bad_def},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" in data
    assert any("orphan" in e.lower() for e in data["errors"])


@pytest.mark.asyncio
async def test_validate_missing_nodes(client: AsyncClient):
    resp = await client.post(
        "/api/workflows/validate",
        json={"name": "Empty", "definition": {"edges": [{"from": "START", "to": "END"}]}},
    )
    data = resp.json()
    assert "errors" in data


@pytest.mark.asyncio
async def test_get_templates(client: AsyncClient):
    resp = await client.get("/api/workflows/templates")
    assert resp.status_code == 200
    templates = resp.json()
    assert len(templates) >= 2
    names = [t["name"] for t in templates]
    assert "courtroom_debate_v3" in names
    assert "quick_analysis" in names
