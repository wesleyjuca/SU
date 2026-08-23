"""Fase 220 (achado da Fase 219) — mesma classe de lacuna que a Fase
176.3/210 fecharam pra ClientContact/ClientInteraction/Opportunity:
`erase_client_data`/`export_client_data` não alcançavam
`GovRegistryLookup` (Fase 217, guarda CPF/CNPJ cifrado consultado
contra a SERPRO). Confirmado empiricamente (HTTP real, Fase 219) que o
CPF sobrevivia decifrável ao "esquecimento" inteiro."""
import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.anyio


async def test_lgpd_erasure_reaches_gov_registry_lookup(client: AsyncClient, auth_headers: dict):
    create_res = await client.post(
        "/api/v1/clients",
        json={"tipo": "PF", "nome_completo": "Titular GovRegistry Fase220", "cpf": "12345678909", "lgpd_consent": True},
        headers=auth_headers,
    )
    if create_res.status_code != 201:
        pytest.skip("Could not create client")
    client_id = create_res.json()["id"]

    validar_res = await client.post(
        "/api/v1/clients/validar-documento",
        json={"tipo": "cpf", "valor": "123.456.789-09"},
        headers=auth_headers,
    )
    assert validar_res.status_code == 200

    export_antes = await client.get(f"/api/v1/lgpd/clients/{client_id}/export", headers=auth_headers)
    assert export_antes.status_code == 200
    consultas_antes = export_antes.json().get("consultas_documentais", [])
    assert len(consultas_antes) == 1

    erase_res = await client.delete(f"/api/v1/lgpd/clients/{client_id}/data", headers=auth_headers)
    if erase_res.status_code != 200:
        pytest.skip("Erasure not permitted for this role")

    export_depois = await client.get(f"/api/v1/lgpd/clients/{client_id}/export", headers=auth_headers)
    assert export_depois.status_code == 200
    consultas_depois = export_depois.json().get("consultas_documentais", [])
    assert consultas_depois == []
    assert "12345678909" not in str(export_depois.json())
