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
    """Rodada pós-260.5 — este teste trocava a senha do ADMIN semeado e
    nunca a restaurava. Enquanto a suíte nem era coletada no CI (ver
    pytest.ini/deploy.yml) isso passou despercebido; assim que ela voltou a
    rodar, a primeira execução inutilizou o login do seed e derrubou toda
    verificação seguinte da sessão. Agora desfaz o que fez."""
    nova_senha = "NewPass@456"
    res = await client.patch(
        "/api/v1/auth/password",
        json={"current_password": test_user["password"], "new_password": nova_senha},
        headers=auth_headers,
    )
    assert res.status_code == 200

    # Restaura para o teste ser repetível e não quebrar o ambiente.
    relogin = await client.post("/api/v1/auth/login",
                                json={"email": test_user["email"], "password": nova_senha})
    assert relogin.status_code == 200
    novo_header = {"Authorization": f"Bearer {relogin.json()['access_token']}"}
    volta = await client.patch(
        "/api/v1/auth/password",
        json={"current_password": nova_senha, "new_password": test_user["password"]},
        headers=novo_header,
    )
    assert volta.status_code == 200



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
