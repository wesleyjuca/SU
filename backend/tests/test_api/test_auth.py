"""Tests for authentication endpoints."""
import pytest



async def test_login_success(client, test_user):
    res = await client.post("/api/v1/auth/login", json={
        "email": test_user["email"],
        "password": test_user["password"],
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == test_user["email"]



async def test_login_wrong_password(client, test_user):
    res = await client.post("/api/v1/auth/login", json={
        "email": test_user["email"],
        "password": "wrongpassword",
    })
    assert res.status_code == 401



async def test_login_unknown_email(client):
    res = await client.post("/api/v1/auth/login", json={
        "email": "nonexistent@test.com",
        "password": "any",
    })
    assert res.status_code == 401



async def test_refresh_token(client, test_user):
    login_res = await client.post("/api/v1/auth/login", json={
        "email": test_user["email"],
        "password": test_user["password"],
    })
    assert login_res.status_code == 200
    refresh_token = login_res.json()["refresh_token"]

    res = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert res.status_code == 200
    assert "access_token" in res.json()



async def test_logout_invalidates_token(client, auth_headers, test_user):
    login_res = await client.post("/api/v1/auth/login", json={
        "email": test_user["email"],
        "password": test_user["password"],
    })
    refresh_token = login_res.json()["refresh_token"]

    res = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
        headers=auth_headers,
    )
    assert res.status_code == 200

    # Second refresh with same token should fail
    res2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert res2.status_code == 401



async def test_password_change_success(client, auth_headers, test_user):
    res = await client.patch(
        "/api/v1/auth/password",
        json={"current_password": test_user["password"], "new_password": "NewPass@456"},
        headers=auth_headers,
    )
    assert res.status_code == 200



async def test_password_change_wrong_current(client, auth_headers):
    res = await client.patch(
        "/api/v1/auth/password",
        json={"current_password": "wrongpass", "new_password": "NewPass@456"},
        headers=auth_headers,
    )
    assert res.status_code == 401



async def test_unauthenticated_request_denied(client):
    res = await client.get("/api/v1/processes")
    assert res.status_code == 401
