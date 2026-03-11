"""Tests for authentication: register, login, token validation."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.auth.service import create_access_token, decode_access_token, hash_password, verify_password


# ---- Unit tests for service functions ----


class TestPasswordHashing:
    def test_hash_and_verify(self):
        hashed = hash_password("secret123")
        assert verify_password("secret123", hashed)

    def test_wrong_password(self):
        hashed = hash_password("secret123")
        assert not verify_password("wrong", hashed)


class TestJWT:
    def test_create_and_decode(self):
        uid = uuid.uuid4()
        token = create_access_token(uid)
        payload = decode_access_token(token)
        assert payload["sub"] == str(uid)

    def test_invalid_token_raises(self):
        import jwt as pyjwt

        with pytest.raises(pyjwt.PyJWTError):
            decode_access_token("invalid.token.here")


# ---- Integration tests via HTTP client ----


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    resp = await client.post(
        "/api/auth/register",
        json={"username": "testuser", "email": "test@example.com", "password": "secret123"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    body = {"username": "user1", "email": "dup@example.com", "password": "secret123"}
    resp1 = await client.post("/api/auth/register", json=body)
    assert resp1.status_code == 201

    body2 = {"username": "user2", "email": "dup@example.com", "password": "secret123"}
    resp2 = await client.post("/api/auth/register", json=body2)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_register_duplicate_username(client: AsyncClient):
    body = {"username": "sameuser", "email": "a@example.com", "password": "secret123"}
    await client.post("/api/auth/register", json=body)

    body2 = {"username": "sameuser", "email": "b@example.com", "password": "secret123"}
    resp = await client.post("/api/auth/register", json=body2)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_short_password(client: AsyncClient):
    resp = await client.post(
        "/api/auth/register",
        json={"username": "user", "email": "x@example.com", "password": "abc"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    await client.post(
        "/api/auth/register",
        json={"username": "loginuser", "email": "login@example.com", "password": "secret123"},
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "login@example.com", "password": "secret123"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post(
        "/api/auth/register",
        json={"username": "wrongpw", "email": "wrong@example.com", "password": "secret123"},
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "wrong@example.com", "password": "badpass"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    resp = await client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "secret123"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_success(client: AsyncClient):
    reg = await client.post(
        "/api/auth/register",
        json={"username": "meuser", "email": "me@example.com", "password": "secret123"},
    )
    token = reg.json()["access_token"]
    resp = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "meuser"
    assert data["email"] == "me@example.com"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_me_no_token(client: AsyncClient):
    resp = await client.get("/api/auth/me")
    assert resp.status_code in (401, 403)  # depends on FastAPI version


@pytest.mark.asyncio
async def test_me_invalid_token(client: AsyncClient):
    resp = await client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
