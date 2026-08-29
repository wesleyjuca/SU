"""Fase 248.2 — cobertura real (Postgres+HTTP) do caminho de maior risco
financeiro do hub de integrações: o receptor de webhook de pagamento
(`POST /integrations/webhooks/{provider}`) nunca tinha nenhum teste, mocked
ou real (achado da Fase 246). Só o HTTP de SAÍDA pro provedor terceiro é
mockado (mesmo padrão já usado no resto do projeto —
`monkeypatch.setattr(<módulo>.httpx, "AsyncClient", lambda **k: FakeClient())`,
ver `tests/test_unit/test_google_workspace.py`); tudo o resto (login, connect,
fatura, webhook, fatura PAGA, FinancialEntry) passa pelo app real contra
Postgres real.

Também cobre o lifecycle completo connect→status→test→disconnect da
Clicksign via HTTP real — o provedor que ganhou sonda nova na Fase 248.1."""
import json

import pytest
from httpx import AsyncClient

import app.services.payment_gateway as pg
import app.services.integration_hub as ih

pytestmark = pytest.mark.anyio


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class _FakeStripeClient:
    """Cobre os 2 call sites usados pelo fluxo Stripe: criação da checkout
    session (POST) e a re-verificação real feita pelo webhook (GET)."""

    def __init__(self, session_id: str, payment_status: str, invoice_id: str | None):
        self.session_id = session_id
        self.payment_status = payment_status
        self.invoice_id = invoice_id

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, data=None, headers=None):
        return _FakeResponse(200, {"id": self.session_id, "url": "https://checkout.stripe.com/fake-session"})

    async def get(self, url, headers=None):
        return _FakeResponse(200, {
            "payment_status": self.payment_status,
            "metadata": {"invoice_id": self.invoice_id},
        })


class _FakeMercadoPagoClient:
    def __init__(self, preference_id: str, payment_status: str, external_reference: str | None):
        self.preference_id = preference_id
        self.payment_status = payment_status
        self.external_reference = external_reference

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        return _FakeResponse(200, {"id": self.preference_id, "init_point": "https://mp.fake/checkout"})

    async def get(self, url, headers=None):
        return _FakeResponse(200, {
            "status": self.payment_status,
            "external_reference": self.external_reference,
        })


async def _criar_cliente(client: AsyncClient, auth_headers: dict, nome: str) -> str:
    res = await client.post(
        "/api/v1/clients",
        json={"nome_completo": nome, "tipo": "PF", "email": f"{nome.lower()}@teste.com"},
        headers=auth_headers,
    )
    if res.status_code not in (200, 201):
        pytest.skip("Could not create client")
    return res.json()["id"]


async def _criar_e_emitir_fatura(client: AsyncClient, auth_headers: dict, client_id: str) -> str:
    res = await client.post(
        "/api/v1/financial/invoices",
        json={"client_id": client_id, "itens": [{"descricao": "Honorários Fase248", "valor": "800.00"}]},
        headers=auth_headers,
    )
    if res.status_code != 201:
        pytest.skip("Could not create invoice")
    invoice_id = res.json()["id"]
    res = await client.patch(f"/api/v1/financial/invoices/{invoice_id}", json={"status": "EMITIDA"}, headers=auth_headers)
    assert res.status_code == 200
    return invoice_id


async def test_stripe_webhook_confirma_pagamento_cria_financial_entry_e_e_idempotente(
    client: AsyncClient, auth_headers: dict, monkeypatch,
):
    connect_res = await client.post(
        "/api/v1/integrations/hub/stripe/connect", json={"credentials": {"secret_key": "sk_test_fase248"}},
        headers=auth_headers,
    )
    if connect_res.status_code != 200:
        pytest.skip("Could not connect stripe")

    client_id = await _criar_cliente(client, auth_headers, "ClienteStripeWebhook")
    invoice_id = await _criar_e_emitir_fatura(client, auth_headers, client_id)

    session_id = "cs_test_fase248_abc"
    monkeypatch.setattr(pg.httpx, "AsyncClient", lambda **k: _FakeStripeClient(session_id, "paid", invoice_id))

    link_res = await client.post(f"/api/v1/financial/invoices/{invoice_id}/payment-link", headers=auth_headers)
    assert link_res.status_code == 200
    assert link_res.json()["provider"] == "stripe"

    webhook_payload = {
        "type": "checkout.session.completed",
        "data": {"object": {"id": session_id, "metadata": {"invoice_id": invoice_id}}},
    }
    hook_res = await client.post("/api/v1/integrations/webhooks/stripe", json=webhook_payload)
    assert hook_res.status_code == 200
    body = hook_res.json()
    assert body["received"] is True
    assert body["processed"] is True

    inv_res = await client.get(f"/api/v1/financial/invoices?client_id={client_id}", headers=auth_headers)
    invs = [i for i in inv_res.json() if i["id"] == invoice_id]
    assert invs and invs[0]["status"] == "PAGA"

    fin_res = await client.get(f"/api/v1/financial?client_id={client_id}", headers=auth_headers)
    entradas = [e for e in fin_res.json() if "Fase248" in (e.get("descricao") or "")]
    assert len(entradas) == 1
    assert entradas[0]["status"] == "PAGO"

    # Replay do MESMO webhook — idempotente, não deve duplicar a receita.
    hook_res2 = await client.post("/api/v1/integrations/webhooks/stripe", json=webhook_payload)
    assert hook_res2.status_code == 200
    assert hook_res2.json()["reason"] == "já estava paga (idempotente)"

    fin_res2 = await client.get(f"/api/v1/financial?client_id={client_id}", headers=auth_headers)
    entradas2 = [e for e in fin_res2.json() if "Fase248" in (e.get("descricao") or "")]
    assert len(entradas2) == 1  # ainda 1, não duplicou

    await client.delete("/api/v1/integrations/hub/stripe", headers=auth_headers)


async def test_stripe_webhook_rejeita_session_que_nao_bate_com_a_fatura(
    client: AsyncClient, auth_headers: dict, monkeypatch,
):
    connect_res = await client.post(
        "/api/v1/integrations/hub/stripe/connect", json={"credentials": {"secret_key": "sk_test_fase248b"}},
        headers=auth_headers,
    )
    if connect_res.status_code != 200:
        pytest.skip("Could not connect stripe")

    client_id = await _criar_cliente(client, auth_headers, "ClienteStripeMismatch")
    invoice_id = await _criar_e_emitir_fatura(client, auth_headers, client_id)

    session_real = "cs_test_fase248_real"
    monkeypatch.setattr(pg.httpx, "AsyncClient", lambda **k: _FakeStripeClient(session_real, "paid", invoice_id))
    link_res = await client.post(f"/api/v1/financial/invoices/{invoice_id}/payment-link", headers=auth_headers)
    assert link_res.status_code == 200

    # Webhook chega com uma session DIFERENTE da que ficou gravada na fatura.
    webhook_payload = {
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_test_forjada", "metadata": {"invoice_id": invoice_id}}},
    }
    hook_res = await client.post("/api/v1/integrations/webhooks/stripe", json=webhook_payload)
    assert hook_res.status_code == 200
    assert hook_res.json()["reason"] == "session não corresponde à fatura"

    inv_res = await client.get(f"/api/v1/financial/invoices?client_id={client_id}", headers=auth_headers)
    invs = [i for i in inv_res.json() if i["id"] == invoice_id]
    assert invs and invs[0]["status"] == "EMITIDA"  # não virou PAGA

    await client.delete("/api/v1/integrations/hub/stripe", headers=auth_headers)


async def test_mercadopago_webhook_confirma_pagamento(client: AsyncClient, auth_headers: dict, monkeypatch):
    connect_res = await client.post(
        "/api/v1/integrations/hub/mercadopago/connect", json={"credentials": {"access_token": "mp_test_fase248"}},
        headers=auth_headers,
    )
    if connect_res.status_code != 200:
        pytest.skip("Could not connect mercadopago")

    client_id = await _criar_cliente(client, auth_headers, "ClienteMPWebhook")
    invoice_id = await _criar_e_emitir_fatura(client, auth_headers, client_id)

    payment_id = "mp_payment_fase248"
    monkeypatch.setattr(pg.httpx, "AsyncClient", lambda **k: _FakeMercadoPagoClient("pref_fase248", "approved", invoice_id))
    link_res = await client.post(f"/api/v1/financial/invoices/{invoice_id}/payment-link", headers=auth_headers)
    assert link_res.status_code == 200
    assert link_res.json()["provider"] == "mercadopago"

    webhook_payload = {"type": "payment", "data": {"id": payment_id}}
    hook_res = await client.post(f"/api/v1/integrations/webhooks/mercadopago?ref={invoice_id}", json=webhook_payload)
    assert hook_res.status_code == 200
    assert hook_res.json()["processed"] is True

    inv_res = await client.get(f"/api/v1/financial/invoices?client_id={client_id}", headers=auth_headers)
    invs = [i for i in inv_res.json() if i["id"] == invoice_id]
    assert invs and invs[0]["status"] == "PAGA"

    await client.delete("/api/v1/integrations/hub/mercadopago", headers=auth_headers)


async def test_clicksign_lifecycle_connect_status_test_disconnect(client: AsyncClient, auth_headers: dict, monkeypatch):
    # connect
    connect_res = await client.post(
        "/api/v1/integrations/hub/clicksign/connect", json={"credentials": {"api_token": "fake_fase248"}},
        headers=auth_headers,
    )
    if connect_res.status_code != 200:
        pytest.skip("Could not connect clicksign")

    # status — CONECTADA logo após conectar
    status_res = await client.get("/api/v1/integrations/hub", headers=auth_headers)
    item = next(i for i in status_res.json()["integracoes"] if i["provider"] == "clicksign")
    assert item["status"] == "CONECTADA"

    # test — sonda mockada (credencial válida)
    class _FakeClicksignOk:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None, params=None):
            return _FakeResponse(200, {"documents": []})

    monkeypatch.setattr(ih.httpx, "AsyncClient", lambda **k: _FakeClicksignOk())
    test_res = await client.post("/api/v1/integrations/hub/clicksign/test", headers=auth_headers)
    assert test_res.status_code == 200
    assert test_res.json()["ok"] is True

    status_res2 = await client.get("/api/v1/integrations/hub", headers=auth_headers)
    item2 = next(i for i in status_res2.json()["integracoes"] if i["provider"] == "clicksign")
    assert item2["status"] == "CONECTADA"

    # disconnect — Fase 248.1: preserva a linha (sem extra_data pra clicksign,
    # mas confirma que o status muda pra DESCONECTADA sem quebrar).
    disc_res = await client.delete("/api/v1/integrations/hub/clicksign", headers=auth_headers)
    assert disc_res.status_code == 200

    status_res3 = await client.get("/api/v1/integrations/hub", headers=auth_headers)
    item3 = next(i for i in status_res3.json()["integracoes"] if i["provider"] == "clicksign")
    assert item3["status"] == "DESCONECTADA"

    # test após desconectar — sem credencial, sem crash.
    test_res2 = await client.post("/api/v1/integrations/hub/clicksign/test", headers=auth_headers)
    assert test_res2.status_code == 200
    assert test_res2.json()["ok"] is False
