"""Fase 238 (achado da Fase 237) — `erase_client_data` sobrescrevia
`User.full_name` do usuário técnico oculto por trás do link de acesso ao
Portal (Fase 235), mas nunca revogava o `ClientPortalAccess` em si: nem
`revoked_at`, nem `User.is_active`, nem as `Session`s de refresh já
emitidas. Confirmado empiricamente (HTTP real, Fase 237) que um token de
portal capturado ANTES do esquecimento continuava resgatável (`POST
/auth/portal-redeem`) DEPOIS dele — o canal de acesso sobrevivia mesmo
com o dado exibido já anonimizado."""
import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.anyio


async def test_lgpd_erasure_revokes_portal_access_and_kills_sessions(client: AsyncClient, auth_headers: dict):
    create_res = await client.post(
        "/api/v1/clients",
        json={"tipo": "PF", "nome_completo": "Titular Portal Fase238", "lgpd_consent": True},
        headers=auth_headers,
    )
    if create_res.status_code != 201:
        pytest.skip("Could not create client")
    client_id = create_res.json()["id"]

    access_res = await client.post(
        f"/api/v1/clients/{client_id}/portal-access",
        json={"validade_dias": 7},
        headers=auth_headers,
    )
    if access_res.status_code != 200:
        pytest.skip("Could not generate portal access")
    token = access_res.json()["path"].rsplit("/", 1)[-1]

    redeem_res = await client.post("/api/v1/auth/portal-redeem", json={"token": token})
    assert redeem_res.status_code == 200
    refresh_token = redeem_res.json()["refresh_token"]

    erase_res = await client.delete(f"/api/v1/lgpd/clients/{client_id}/data", headers=auth_headers)
    if erase_res.status_code != 200:
        pytest.skip("Erasure not permitted for this role")

    # o MESMO token bruto capturado antes do esquecimento não deve mais
    # conseguir uma sessão nova
    redeem_after = await client.post("/api/v1/auth/portal-redeem", json={"token": token})
    assert redeem_after.status_code == 401

    # a sessão já ativa antes do esquecimento não deve sobreviver (refresh morto)
    refresh_after = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_after.status_code == 401

    status_res = await client.get("/api/v1/clients/portal-access", headers=auth_headers)
    assert status_res.status_code == 200
    row = next((r for r in status_res.json() if r["client_id"] == client_id), None)
    assert row is not None
    assert row["status"] == "REVOGADO"


async def test_lgpd_erasure_without_portal_access_is_noop(client: AsyncClient, auth_headers: dict):
    create_res = await client.post(
        "/api/v1/clients",
        json={"tipo": "PF", "nome_completo": "Titular Sem Portal Fase238", "lgpd_consent": True},
        headers=auth_headers,
    )
    if create_res.status_code != 201:
        pytest.skip("Could not create client")
    client_id = create_res.json()["id"]

    erase_res = await client.delete(f"/api/v1/lgpd/clients/{client_id}/data", headers=auth_headers)
    assert erase_res.status_code == 200
