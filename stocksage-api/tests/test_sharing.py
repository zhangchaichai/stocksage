"""Tests for Sharing endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

_WORKFLOW_DEFINITION = {
    "name": "test_workflow",
    "version": "1.0.0",
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


async def _create_workflow(client: AsyncClient, headers: dict, name: str = "test_wf") -> str:
    """Helper: create a workflow and return its id."""
    resp = await client.post(
        "/api/workflows",
        json={
            "name": name,
            "description": "A test workflow",
            "definition": _WORKFLOW_DEFINITION,
            "version": "1.0.0",
        },
        headers=headers,
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_share_workflow(client: AsyncClient):
    """Share a workflow and get a share URL."""
    headers = await get_auth_header(client)
    wf_id = await _create_workflow(client, headers, "shareable_wf")

    resp = await client.post(f"/api/sharing/workflows/{wf_id}/share", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "share_url" in data
    assert data["workflow_id"] == wf_id
    assert wf_id in data["share_url"]


@pytest.mark.asyncio
async def test_export_workflow(client: AsyncClient):
    """Export a workflow as JSON."""
    headers = await get_auth_header(client)
    wf_id = await _create_workflow(client, headers, "exportable_wf")

    resp = await client.get(f"/api/sharing/workflows/{wf_id}/export", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "exportable_wf"
    assert data["description"] == "A test workflow"
    assert "definition" in data
    assert "nodes" in data["definition"]


@pytest.mark.asyncio
async def test_import_workflow(client: AsyncClient):
    """Import a workflow from JSON."""
    headers = await get_auth_header(client)

    import_body = {
        "name": "imported_workflow",
        "description": "An imported workflow",
        "definition": _WORKFLOW_DEFINITION,
        "version": "2.0.0",
        "skills": [
            {
                "name": "imported_skill",
                "type": "agent",
                "version": "1.0.0",
                "tags": ["imported"],
                "definition_md": "---\nname: imported\n---\n# Imported Skill",
            }
        ],
    }

    resp = await client.post("/api/sharing/workflows/import", json=import_body, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "imported_workflow"
    assert data["skills_imported"] == 1
    assert "workflow_id" in data


@pytest.mark.asyncio
async def test_get_public_workflow(client: AsyncClient):
    """Access a public workflow without authentication."""
    headers = await get_auth_header(client)
    wf_id = await _create_workflow(client, headers, "public_wf")

    # Share it first (sets is_public=True)
    await client.post(f"/api/sharing/workflows/{wf_id}/share", headers=headers)

    # Access without auth
    resp = await client.get(f"/api/sharing/public/{wf_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "public_wf"
    assert data["is_public"] is True
