"""Tests for Runs endpoints (submit, list, get, cancel)."""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

_VALID_DEFINITION = {
    "name": "test_wf",
    "nodes": [{"id": "analyst", "skill": "technical_analyst"}],
    "edges": [
        {"from": "START", "to": "analyst"},
        {"from": "analyst", "to": "END"},
    ],
}


async def _setup_user_and_workflow(client: AsyncClient, username="runuser", email="run@example.com"):
    """Register user, create workflow, return (token, workflow_id)."""
    reg = await client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": "secret123"},
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    wf = await client.post(
        "/api/workflows",
        json={"name": "Test WF", "definition": _VALID_DEFINITION},
        headers=headers,
    )
    return token, wf.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_submit_run(client: AsyncClient):
    token, wf_id = await _setup_user_and_workflow(client)
    resp = await client.post(
        "/api/runs",
        json={"workflow_id": wf_id, "symbol": "600519", "stock_name": "贵州茅台"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "queued"
    assert data["symbol"] == "600519"
    assert data["workflow_id"] == wf_id


@pytest.mark.asyncio
async def test_submit_run_invalid_workflow(client: AsyncClient):
    reg = await client.post(
        "/api/auth/register",
        json={"username": "badwf", "email": "badwf@example.com", "password": "secret123"},
    )
    token = reg.json()["access_token"]
    resp = await client.post(
        "/api/runs",
        json={"workflow_id": "00000000-0000-0000-0000-000000000000", "symbol": "AAPL"},
        headers=_auth(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_runs(client: AsyncClient):
    token, wf_id = await _setup_user_and_workflow(client, "listrunuser", "listrun@example.com")
    headers = _auth(token)

    await client.post("/api/runs", json={"workflow_id": wf_id, "symbol": "AAPL"}, headers=headers)
    await client.post("/api/runs", json={"workflow_id": wf_id, "symbol": "GOOGL"}, headers=headers)

    resp = await client.get("/api/runs", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_get_run(client: AsyncClient):
    token, wf_id = await _setup_user_and_workflow(client, "getrunuser", "getrun@example.com")
    headers = _auth(token)

    create_resp = await client.post(
        "/api/runs", json={"workflow_id": wf_id, "symbol": "TSLA"}, headers=headers,
    )
    run_id = create_resp.json()["id"]

    resp = await client.get(f"/api/runs/{run_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["symbol"] == "TSLA"


@pytest.mark.asyncio
async def test_cancel_run(client: AsyncClient):
    token, wf_id = await _setup_user_and_workflow(client, "canceluser", "cancel@example.com")
    headers = _auth(token)

    create_resp = await client.post(
        "/api/runs", json={"workflow_id": wf_id, "symbol": "MSFT"}, headers=headers,
    )
    run_id = create_resp.json()["id"]

    # Cancel (dispatch is mocked, so run stays "queued")
    resp = await client.delete(f"/api/runs/{run_id}", headers=headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_run_isolation(client: AsyncClient):
    token_a, wf_id_a = await _setup_user_and_workflow(client, "isoA", "isoa@example.com")
    token_b, _ = await _setup_user_and_workflow(client, "isoB", "isob@example.com")

    create_resp = await client.post(
        "/api/runs",
        json={"workflow_id": wf_id_a, "symbol": "NVDA"},
        headers=_auth(token_a),
    )
    run_id = create_resp.json()["id"]

    resp = await client.get(f"/api/runs/{run_id}", headers=_auth(token_b))
    assert resp.status_code == 404
