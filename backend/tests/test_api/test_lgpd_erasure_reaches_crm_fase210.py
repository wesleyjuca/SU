"""Fase 210 (achado da Fase 209) — mesma classe de lacuna que a Fase 176.3
fechou pra ClientContact/ClientInteraction: `erase_client_data` não
alcançava `Opportunity` (CRM, Fase 161/208.2), que tem `client_id` e campos
de texto livre (`descricao`/`motivo_perda`) que podem conter PII do
titular. Confirmado empiricamente (HTTP real, Fase 209) que sobrevivia ao
"esquecimento" e continuava visível em GET /crm/opportunities."""
import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.anyio


async def test_lgpd_erasure_reaches_opportunity_descricao(client: AsyncClient, auth_headers: dict):
    create_res = await client.post(
        "/api/v1/clients",
        json={"tipo": "PF", "nome_completo": "Titular CRM Fase210", "lgpd_consent": True},
        headers=auth_headers,
    )
    if create_res.status_code != 201:
        pytest.skip("Could not create client")
    client_id = create_res.json()["id"]

    opp_res = await client.post(
        "/api/v1/crm/opportunities",
        json={
            "titulo": "Consultoria trabalhista",
            "client_id": client_id,
            "descricao": "Cliente CPF 123.456.789-00, telefone 11988887777, relatou disputa com ex-empregador",
            "estagio": "PERDIDO",
            "motivo_perda": "Contato 11988887777 desistiu",
        },
        headers=auth_headers,
    )
    if opp_res.status_code != 201:
        pytest.skip("Could not create opportunity")
    opp_id = opp_res.json()["id"]

    erase_res = await client.delete(f"/api/v1/lgpd/clients/{client_id}/data", headers=auth_headers)
    if erase_res.status_code != 200:
        pytest.skip("Erasure not permitted for this role")

    list_res = await client.get("/api/v1/crm/opportunities", headers=auth_headers)
    assert list_res.status_code == 200
    assert "11988887777" not in str(list_res.json())
    assert "123.456.789-00" not in str(list_res.json())

    export_res = await client.get(f"/api/v1/lgpd/clients/{client_id}/export", headers=auth_headers)
    assert export_res.status_code == 200
    exported = export_res.json()
    assert "11988887777" not in str(exported)
    assert any(o["titulo"] == "Consultoria trabalhista" for o in exported.get("oportunidades_crm", []))

    await client.delete(f"/api/v1/crm/opportunities/{opp_id}", headers=auth_headers)
