"""Tests for Reports endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WorkflowRun

_VALID_DEFINITION = {
    "name": "test_wf",
    "nodes": [{"id": "analyst", "skill": "x"}],
    "edges": [{"from": "START", "to": "analyst"}, {"from": "analyst", "to": "END"}],
}


async def _setup_completed_run(client: AsyncClient, db_session: AsyncSession):
    """Create a user, workflow, and a completed run, return (token, run_id)."""
    reg = await client.post(
        "/api/auth/register",
        json={"username": "rptuser", "email": "rpt@example.com", "password": "secret123"},
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    wf = await client.post(
        "/api/workflows",
        json={"name": "Report WF", "definition": _VALID_DEFINITION},
        headers=headers,
    )
    wf_id = wf.json()["id"]

    # Submit run (dispatch is mocked, so it stays queued)
    run_resp = await client.post(
        "/api/runs",
        json={"workflow_id": wf_id, "symbol": "600519", "stock_name": "贵州茅台"},
        headers=headers,
    )
    run_id = uuid.UUID(run_resp.json()["id"])

    # Manually set run to "completed" with a result
    from sqlalchemy import select
    result = await db_session.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))
    run = result.scalar_one()
    run.status = "completed"
    run.result = {"summary": "Test completed", "recommendation": "Buy"}
    run.completed_at = datetime.now(timezone.utc)
    await db_session.flush()

    return token, str(run_id)


@pytest.mark.asyncio
async def test_get_markdown_report(client: AsyncClient, db_session: AsyncSession):
    token, run_id = await _setup_completed_run(client, db_session)
    resp = await client.get(
        f"/api/reports/{run_id}/markdown",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
    assert "600519" in resp.text
    assert "StockSage" in resp.text


@pytest.mark.asyncio
async def test_get_pdf_report(client: AsyncClient, db_session: AsyncSession):
    token, run_id = await _setup_completed_run(client, db_session)
    resp = await client.get(
        f"/api/reports/{run_id}/pdf",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "content-disposition" in resp.headers


@pytest.mark.asyncio
async def test_report_not_found(client: AsyncClient):
    reg = await client.post(
        "/api/auth/register",
        json={"username": "rptnf", "email": "rptnf@example.com", "password": "secret123"},
    )
    token = reg.json()["access_token"]
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.get(
        f"/api/reports/{fake_id}/markdown",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_report_run_not_finished(client: AsyncClient):
    reg = await client.post(
        "/api/auth/register",
        json={"username": "rptpending", "email": "rptpend@example.com", "password": "secret123"},
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    wf = await client.post(
        "/api/workflows",
        json={"name": "WF", "definition": _VALID_DEFINITION},
        headers=headers,
    )
    wf_id = wf.json()["id"]

    run_resp = await client.post(
        "/api/runs",
        json={"workflow_id": wf_id, "symbol": "AAPL"},
        headers=headers,
    )
    run_id = run_resp.json()["id"]

    # Run is still "queued", so report should be 409
    resp = await client.get(
        f"/api/reports/{run_id}/markdown",
        headers=headers,
    )
    assert resp.status_code == 409
