async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") in ("ok", "operational", "healthy")


async def test_login_wrong_password(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@test.com", "password": "wrongpassword"},
    )
    assert response.status_code in (401, 422)


async def test_processes_requires_auth(client):
    response = await client.get("/api/v1/processes")
    assert response.status_code == 401
