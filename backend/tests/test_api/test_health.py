async def test_health(client):
    """O status precisa ser COERENTE com os componentes reportados.

    A asserção anterior exigia `status == "operational"`, o que só vale num
    ambiente com Postgres E Redis de pé. No CI só existe Postgres (não há
    serviço de Redis no job), então `/health` respondia `degraded` — que é a
    resposta CERTA — e o teste reprovava por causa do ambiente, não do
    código. Foi assim que ele quebrou no primeiro run em que a suíte de API
    virou gate: local com Redis dizia "operational", CI sem Redis dizia
    "degraded".

    Verificar a coerência dá mais sinal do que verificar o literal: pega tanto
    um "operational" mentiroso (com componente crítico fora) quanto um
    "degraded" espúrio (com tudo de pé) — e vale em qualquer ambiente.
    """
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()

    assert data.get("status") in ("operational", "degraded"), data
    checks = data.get("checks") or {}
    assert {"postgresql", "redis", "qdrant"} <= set(checks), checks

    # Só postgres e redis são críticos; qdrant (RAG) é opcional — mesma regra
    # do endpoint (`app/main.py`).
    criticos_ok = checks["postgresql"] and checks["redis"]
    esperado = "operational" if criticos_ok else "degraded"
    assert data["status"] == esperado, (
        f"status={data['status']} não bate com os componentes {checks}"
    )


async def test_login_wrong_password(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@test.com", "password": "wrongpassword"},
    )
    assert response.status_code in (401, 422)


async def test_processes_requires_auth(client):
    response = await client.get("/api/v1/processes")
    assert response.status_code == 401
