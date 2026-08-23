"""Fase 228 (teste geral) — 4ª ocorrência da mesma classe de lacuna já
fechada 3x antes (Fase 176.3→ClientContact/ClientInteraction, Fase
210→Opportunity, Fase 220→GovRegistryLookup): `erase_client_data` não
alcançava `ProcessParty` (nome/cpf_cnpj em texto puro), `FinancialEntry.
descricao` nem `BillingInvoice.descricao`/`.itens`. Confirmado
empiricamente (HTTP real, Fase 228) que o PII original sobrevivia ao
"esquecimento" nas 3 tabelas."""
import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.anyio


async def test_lgpd_erasure_reaches_process_party(client: AsyncClient, auth_headers: dict):
    create_res = await client.post(
        "/api/v1/clients",
        json={"tipo": "PF", "nome_completo": "Titular Parte Fase228", "lgpd_consent": True},
        headers=auth_headers,
    )
    if create_res.status_code != 201:
        pytest.skip("Could not create client")
    client_id = create_res.json()["id"]

    proc_res = await client.post(
        "/api/v1/processes",
        json={"tribunal": "TJAC", "tipo_acao": "Fase228 teste"},
        headers=auth_headers,
    )
    if proc_res.status_code != 201:
        pytest.skip("Could not create process")
    process_id = proc_res.json()["id"]

    party_res = await client.post(
        f"/api/v1/processes/{process_id}/partes",
        json={
            "tipo": "AUTOR",
            "nome": "Titular Parte Fase228",
            "cpf_cnpj": "111.222.333-44",
            "polo": "ATIVO",
            "client_id": client_id,
        },
        headers=auth_headers,
    )
    if party_res.status_code != 201:
        pytest.skip("Could not create process party")

    erase_res = await client.delete(f"/api/v1/lgpd/clients/{client_id}/data", headers=auth_headers)
    if erase_res.status_code != 200:
        pytest.skip("Erasure not permitted for this role")

    list_res = await client.get(f"/api/v1/processes/{process_id}/partes", headers=auth_headers)
    assert list_res.status_code == 200
    assert "Titular Parte Fase228" not in str(list_res.json())
    assert "111.222.333-44" not in str(list_res.json())

    export_res = await client.get(f"/api/v1/lgpd/clients/{client_id}/export", headers=auth_headers)
    assert export_res.status_code == 200
    exported = export_res.json()
    assert "111.222.333-44" not in str(exported)


async def test_lgpd_erasure_reaches_financial_entry_descricao(client: AsyncClient, auth_headers: dict):
    create_res = await client.post(
        "/api/v1/clients",
        json={"tipo": "PF", "nome_completo": "Titular Financeiro Fase228", "lgpd_consent": True},
        headers=auth_headers,
    )
    if create_res.status_code != 201:
        pytest.skip("Could not create client")
    client_id = create_res.json()["id"]

    entry_res = await client.post(
        "/api/v1/financial",
        json={
            "tipo": "RECEITA",
            "categoria": "HONORARIOS",
            "client_id": client_id,
            "descricao": "Honorarios de Titular Financeiro Fase228, CPF 555.666.777-88",
            "valor": 1500.00,
        },
        headers=auth_headers,
    )
    if entry_res.status_code != 201:
        pytest.skip("Could not create financial entry")
    entry_id = entry_res.json()["id"]

    erase_res = await client.delete(f"/api/v1/lgpd/clients/{client_id}/data", headers=auth_headers)
    if erase_res.status_code != 200:
        pytest.skip("Erasure not permitted for this role")

    list_res = await client.get("/api/v1/financial", params={"client_id": client_id}, headers=auth_headers)
    assert list_res.status_code == 200
    assert "555.666.777-88" not in str(list_res.json())
    # valor não é PII — precisa sobreviver ao esquecimento.
    assert "1500" in str(list_res.json())

    export_res = await client.get(f"/api/v1/lgpd/clients/{client_id}/export", headers=auth_headers)
    assert export_res.status_code == 200
    exported = export_res.json()
    assert "555.666.777-88" not in str(exported)

    await client.delete(f"/api/v1/financial/{entry_id}", headers=auth_headers)


async def test_lgpd_erasure_reaches_billing_invoice(client: AsyncClient, auth_headers: dict):
    create_res = await client.post(
        "/api/v1/clients",
        json={"tipo": "PF", "nome_completo": "Titular Fatura Fase228", "lgpd_consent": True},
        headers=auth_headers,
    )
    if create_res.status_code != 201:
        pytest.skip("Could not create client")
    client_id = create_res.json()["id"]

    invoice_res = await client.post(
        "/api/v1/financial/invoices",
        json={
            "client_id": client_id,
            "descricao": "Fatura de Titular Fatura Fase228, CPF 999.888.777-66",
            "itens": [{"descricao": "Consulta jurídica para Titular Fatura Fase228", "valor": "500.00"}],
        },
        headers=auth_headers,
    )
    if invoice_res.status_code != 201:
        pytest.skip("Could not create billing invoice")
    invoice_id = invoice_res.json()["id"]

    erase_res = await client.delete(f"/api/v1/lgpd/clients/{client_id}/data", headers=auth_headers)
    if erase_res.status_code != 200:
        pytest.skip("Erasure not permitted for this role")

    list_res = await client.get("/api/v1/financial/invoices", params={"client_id": client_id}, headers=auth_headers)
    assert list_res.status_code == 200
    body = next(inv for inv in list_res.json() if inv["id"] == invoice_id)
    assert "999.888.777-66" not in str(body)
    assert "Titular Fatura Fase228" not in str(body)
    # valor de cada item não é PII — precisa sobreviver ao esquecimento.
    assert "500" in str(body)

    export_res = await client.get(f"/api/v1/lgpd/clients/{client_id}/export", headers=auth_headers)
    assert export_res.status_code == 200
    exported = export_res.json()
    assert "999.888.777-66" not in str(exported)
