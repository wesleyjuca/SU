"""Fase 180 — exclusão PERMANENTE de processo/usuário, restrita ao SUPERADMIN,
e a trava de segurança `Tenant.em_producao` que bloqueia essas exclusões.
Usa `superadmin_headers` (conftest.py) — pula graciosamente se o seed
SUPERADMIN não estiver disponível no ambiente, mesmo espírito de `auth_headers`."""
import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.anyio


async def test_processo_permanente_recusado_para_nao_superadmin(client: AsyncClient, auth_headers: dict):
    """auth_headers é ADMIN (não SUPERADMIN) — deve ser barrado."""
    create_res = await client.post(
        "/api/v1/processes",
        json={"numero_cnj": "0000009-00.2024.8.26.0100", "tribunal": "TJSP"},
        headers=auth_headers,
    )
    if create_res.status_code != 201:
        pytest.skip("Could not create process")
    process_id = create_res.json()["id"]

    res = await client.delete(f"/api/v1/processes/{process_id}/permanente", headers=auth_headers)
    assert res.status_code == 403


async def test_processo_permanente_superadmin_apaga_de_verdade(
    client: AsyncClient, auth_headers: dict, superadmin_headers: dict
):
    create_res = await client.post(
        "/api/v1/processes",
        json={"numero_cnj": "0000010-00.2024.8.26.0100", "tribunal": "TJSP"},
        headers=auth_headers,
    )
    if create_res.status_code != 201:
        pytest.skip("Could not create process")
    process_id = create_res.json()["id"]

    del_res = await client.delete(f"/api/v1/processes/{process_id}/permanente", headers=superadmin_headers)
    assert del_res.status_code == 204

    get_res = await client.get(f"/api/v1/processes/{process_id}", headers=auth_headers)
    assert get_res.status_code == 404


async def test_usuario_permanente_recusado_para_nao_superadmin(client: AsyncClient, auth_headers: dict):
    invite_res = await client.post(
        "/api/v1/users/invite",
        json={"email": "descartavel180a@afjadvogados.com.br", "full_name": "Descartável 180a", "role": "ASSISTENTE"},
        headers=auth_headers,
    )
    if invite_res.status_code != 201:
        pytest.skip("Could not create user")
    user_id = invite_res.json()["id"]

    res = await client.delete(f"/api/v1/users/{user_id}/permanente", headers=auth_headers)
    assert res.status_code == 403


async def test_usuario_permanente_superadmin_nao_pode_excluir_a_si_mesmo(
    client: AsyncClient, superadmin_headers: dict
):
    me_res = await client.get("/api/v1/users/me", headers=superadmin_headers)
    if me_res.status_code != 200:
        pytest.skip("Could not fetch current user")
    me_id = me_res.json()["id"]

    res = await client.delete(f"/api/v1/users/{me_id}/permanente", headers=superadmin_headers)
    assert res.status_code == 422


async def test_usuario_permanente_superadmin_apaga_de_verdade(
    client: AsyncClient, auth_headers: dict, superadmin_headers: dict
):
    invite_res = await client.post(
        "/api/v1/users/invite",
        json={"email": "descartavel180b@afjadvogados.com.br", "full_name": "Descartável 180b", "role": "ASSISTENTE"},
        headers=auth_headers,
    )
    if invite_res.status_code != 201:
        pytest.skip("Could not create user")
    user_id = invite_res.json()["id"]

    del_res = await client.delete(f"/api/v1/users/{user_id}/permanente", headers=superadmin_headers)
    assert del_res.status_code == 204

    list_res = await client.get("/api/v1/users", headers=auth_headers)
    assert list_res.status_code == 200
    assert not any(u["id"] == user_id for u in list_res.json())


async def test_tenant_em_producao_bloqueia_exclusao_permanente(
    client: AsyncClient, auth_headers: dict, superadmin_headers: dict
):
    me_res = await client.get("/api/v1/users/me", headers=auth_headers)
    if me_res.status_code != 200:
        pytest.skip("Could not fetch current user")
    tenant_id = me_res.json().get("tenant_id")
    if not tenant_id:
        pytest.skip("Current user has no tenant_id")

    create_res = await client.post(
        "/api/v1/processes",
        json={"numero_cnj": "0000011-00.2024.8.26.0100", "tribunal": "TJSP"},
        headers=auth_headers,
    )
    if create_res.status_code != 201:
        pytest.skip("Could not create process")
    process_id = create_res.json()["id"]

    patch_res = await client.patch(f"/api/v1/tenants/{tenant_id}", json={"em_producao": True}, headers=superadmin_headers)
    if patch_res.status_code != 200:
        pytest.skip("Could not toggle em_producao")

    try:
        blocked_res = await client.delete(f"/api/v1/processes/{process_id}/permanente", headers=superadmin_headers)
        assert blocked_res.status_code == 403
    finally:
        # Sempre reverte a trava, mesmo se a asserção acima falhar, pra não
        # vazar estado pros outros testes deste arquivo/rodada.
        await client.patch(f"/api/v1/tenants/{tenant_id}", json={"em_producao": False}, headers=superadmin_headers)
        await client.delete(f"/api/v1/processes/{process_id}/permanente", headers=superadmin_headers)
