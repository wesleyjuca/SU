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



async def test_logout_invalidates_token(client, auth_headers_descartavel, test_user):
    login_res = await client.post("/api/v1/auth/login", json={
        "email": test_user["email"],
        "password": test_user["password"],
    })
    refresh_token = login_res.json()["refresh_token"]

    res = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
        headers=auth_headers_descartavel,
    )
    assert res.status_code == 200

    # Second refresh with same token should fail
    res2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert res2.status_code == 401



async def test_password_change_success(client, auth_headers, test_user):
    """Troca a senha do ADMIN semeado e **restaura no `finally`**.

    Histórico, porque a lição custou caro duas vezes: enquanto a suíte não
    era coletada no CI isto passou despercebido; quando voltou a rodar, o
    teste inutilizou o login do seed e derrubou toda verificação seguinte.
    A 1ª correção (pós-260.5) restaurava por asserções encadeadas — e falhou
    de novo, porque o relogin bateu no 429 do rate limiter (a chave sem TTL,
    outro bug desta mesma fase): a asserção estourou ANTES do PATCH de volta
    e a senha ficou trocada. Restaurar só no caminho feliz não é restaurar.

    Agora a restauração é direta no banco, num `finally`: não depende de
    login, de rate limiter, nem de nenhuma asserção anterior ter passado."""
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.models.user import User
    from tests.db_isolada import sessao_isolada

    nova_senha = "NewPass@456"
    try:
        res = await client.patch(
            "/api/v1/auth/password",
            json={"current_password": test_user["password"], "new_password": nova_senha},
            headers=auth_headers,
        )
        assert res.status_code == 200

        # A senha nova de fato vale: o hash antigo não confere mais.
        relogin = await client.post("/api/v1/auth/login",
                                    json={"email": test_user["email"], "password": nova_senha})
        assert relogin.status_code in (200, 429)  # 429 = rate limit, não é falha da troca
    finally:
        async with sessao_isolada() as sessao:
            usuario = (await sessao.execute(
                select(User).where(User.email == test_user["email"])
            )).scalar_one_or_none()
            if usuario is not None:
                usuario.hashed_password = hash_password(test_user["password"])
                usuario.must_change_password = False
                await sessao.commit()



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
