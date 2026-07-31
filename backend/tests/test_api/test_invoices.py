"""Fase 129 — faturamento: idempotência de criação, precisão Decimal, aviso de vencimento."""
import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.anyio


async def _criar_cliente(client: AsyncClient, auth_headers: dict, nome: str) -> str:
    res = await client.post(
        "/api/v1/clients",
        json={"nome_completo": nome, "tipo": "PF", "email": f"{nome.lower()}@teste.com"},
        headers=auth_headers,
    )
    if res.status_code not in (200, 201):
        pytest.skip("Could not create client")
    return res.json()["id"]


async def test_create_invoice_persiste_valor_com_precisao(client: AsyncClient, auth_headers: dict):
    client_id = await _criar_cliente(client, auth_headers, "ClienteFatura1")
    res = await client.post(
        "/api/v1/financial/invoices",
        json={"client_id": client_id, "itens": [{"descricao": "Honorários", "valor": "150.33"}]},
        headers=auth_headers,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["valor_total"] == 150.33
    # Fase 129 — itens[].valor grava string (Decimal-safe), não float
    assert data["itens"][0]["valor"] == "150.33"


async def test_create_invoice_bloqueia_duplicata_recente(client: AsyncClient, auth_headers: dict):
    client_id = await _criar_cliente(client, auth_headers, "ClienteFatura2")
    payload = {"client_id": client_id, "itens": [{"descricao": "Honorários", "valor": "200.00"}]}

    res1 = await client.post("/api/v1/financial/invoices", json=payload, headers=auth_headers)
    assert res1.status_code == 201

    res2 = await client.post("/api/v1/financial/invoices", json=payload, headers=auth_headers)
    assert res2.status_code == 409
    assert "fatura recente" in res2.json()["detail"]


async def test_create_invoice_valores_diferentes_nao_bloqueia(client: AsyncClient, auth_headers: dict):
    client_id = await _criar_cliente(client, auth_headers, "ClienteFatura3")
    res1 = await client.post(
        "/api/v1/financial/invoices",
        json={"client_id": client_id, "itens": [{"descricao": "A", "valor": "100.00"}]},
        headers=auth_headers,
    )
    assert res1.status_code == 201
    res2 = await client.post(
        "/api/v1/financial/invoices",
        json={"client_id": client_id, "itens": [{"descricao": "B", "valor": "999.00"}]},
        headers=auth_headers,
    )
    assert res2.status_code == 201


async def test_create_invoice_vencimento_no_passado_gera_aviso(client: AsyncClient, auth_headers: dict):
    client_id = await _criar_cliente(client, auth_headers, "ClienteFatura4")
    res = await client.post(
        "/api/v1/financial/invoices",
        json={
            "client_id": client_id,
            "itens": [{"descricao": "Honorários", "valor": "50.00"}],
            "data_vencimento": "2020-01-01",
        },
        headers=auth_headers,
    )
    assert res.status_code == 201
    assert "passou" in res.json().get("aviso", "")
