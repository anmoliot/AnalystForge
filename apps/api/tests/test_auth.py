"""Tests for authentication, authorization (RBAC), token rotation, 2FA and API keys."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_register_and_login_flow(client: httpx.AsyncClient) -> None:
    # 1. Register
    reg_payload = {
        "email": "analyst@apexcap.com",
        "password": "Password123!",
        "full_name": "Jane Doe",
        "tenant_name": "Apex Capital",
    }
    resp = await client.post("/api/v1/auth/register", json=reg_payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["email"] == "analyst@apexcap.com"
    assert data["role"] == "ADMIN"  # First user in tenant is ADMIN

    # 2. Login
    login_payload = {
        "email": "analyst@apexcap.com",
        "password": "Password123!",
    }
    resp = await client.post("/api/v1/auth/login", json=login_payload)
    assert resp.status_code == 200, resp.text
    tokens = resp.json()
    assert "access_token" in tokens
    assert tokens["token_type"] == "bearer"
    access_token = tokens["access_token"]

    # 3. /me with Bearer token
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200
    me = resp.json()
    assert me["email"] == "analyst@apexcap.com"
    assert me["full_name"] == "Jane Doe"

    # 4. Refresh token rotation
    refresh_cookie = resp.cookies.get("refresh_token") or client.cookies.get("refresh_token")
    if refresh_cookie:
        resp = await client.post("/api/v1/auth/refresh")
        assert resp.status_code == 200
        new_tokens = resp.json()
        assert "access_token" in new_tokens

    # 5. Logout
    resp = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_duplicate_registration_rejected(client: httpx.AsyncClient) -> None:
    payload = {
        "email": "dupe@example.com",
        "password": "Password123!",
        "full_name": "Dupe User",
        "tenant_name": "Dupe Tenant",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201

    resp2 = await client.post("/api/v1/auth/register", json=payload)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_invalid_login_credentials(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": "WrongPassword1!"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_key_lifecycle(client: httpx.AsyncClient) -> None:
    # Register user
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "apikey_user@example.com",
            "password": "Password123!",
            "full_name": "API Tester",
            "tenant_name": "API Testing Org",
        },
    )
    assert reg.status_code == 201

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "apikey_user@example.com", "password": "Password123!"},
    )
    access_token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # Create API key
    key_resp = await client.post(
        "/api/v1/auth/api-keys",
        headers=headers,
        json={"name": "Test Script Key", "expires_days": 30},
    )
    assert key_resp.status_code == 201
    key_data = key_resp.json()
    assert "full_key" in key_data
    assert key_data["full_key"].startswith("af_")
    full_key = key_data["full_key"]
    key_id = key_data["id"]

    # Use API key to access /me
    api_headers = {"Authorization": f"Bearer {full_key}"}
    me_resp = await client.get("/api/v1/auth/me", headers=api_headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "apikey_user@example.com"

    # List API keys
    list_resp = await client.get("/api/v1/auth/api-keys", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # Revoke API key
    del_resp = await client.delete(f"/api/v1/auth/api-keys/{key_id}", headers=headers)
    assert del_resp.status_code == 204

    # Now using the key should fail
    fail_resp = await client.get("/api/v1/auth/me", headers=api_headers)
    assert fail_resp.status_code == 401


@pytest.mark.asyncio
async def test_totp_setup_and_verify(client: httpx.AsyncClient) -> None:
    import pyotp

    # Register
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "totp_user@example.com",
            "password": "Password123!",
            "full_name": "TOTP User",
            "tenant_name": "Security Org",
        },
    )
    assert reg.status_code == 201

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "totp_user@example.com", "password": "Password123!"},
    )
    access_token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # Setup TOTP
    setup = await client.post("/api/v1/auth/totp/setup", headers=headers)
    assert setup.status_code == 200
    setup_data = setup.json()
    assert "secret" in setup_data
    secret = setup_data["secret"]

    # Generate valid code
    totp = pyotp.TOTP(secret)
    code = totp.now()

    # Verify
    verify = await client.post(
        "/api/v1/auth/totp/verify",
        headers=headers,
        json={"code": code},
    )
    assert verify.status_code == 204

    # Check /me reports totp_enabled = true
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["totp_enabled"] is True

    # Login without TOTP code now fails
    login_fail = await client.post(
        "/api/v1/auth/login",
        json={"email": "totp_user@example.com", "password": "Password123!"},
    )
    assert login_fail.status_code == 401
    msg = login_fail.json()["error"]["message"]
    assert "TOTP" in msg or "2FA" in msg

    # Login with TOTP code succeeds
    code2 = totp.now()
    login_success = await client.post(
        "/api/v1/auth/login",
        json={"email": "totp_user@example.com", "password": "Password123!", "totp_code": code2},
    )
    assert login_success.status_code == 200


@pytest.mark.asyncio
async def test_refresh_token_reuse_attack_rejected(client: httpx.AsyncClient) -> None:
    # Register & Login
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "token_reuse@example.com",
            "password": "Password123!",
            "full_name": "Reuse Tester",
            "tenant_name": "Reuse Org",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "token_reuse@example.com", "password": "Password123!"},
    )
    refresh_token = login.cookies.get("refresh_token")
    assert refresh_token is not None

    # First refresh succeeds
    client.cookies.set("refresh_token", refresh_token)
    ref1 = await client.post("/api/v1/auth/refresh")
    assert ref1.status_code == 200

    # Second refresh with OLD token must fail (reuse attack detected)
    client.cookies.set("refresh_token", refresh_token)
    ref2 = await client.post("/api/v1/auth/refresh")
    assert ref2.status_code == 401
    assert "already used" in ref2.json()["error"]["message"]
