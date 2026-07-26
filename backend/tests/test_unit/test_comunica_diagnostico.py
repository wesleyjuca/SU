"""Fase 114 — a mensagem "fonte não respondeu" da captura por OAB descartava
a causa real (exceção de rede vs. HTTP não-200 da própria Comunica). Confirma
que buscar_comunicacoes agora preenche stats['status_code']/stats['error']
nos dois casos, permitindo diagnosticar sem adivinhar."""
from datetime import date

import httpx
import pytest

from app.integrations.dje.comunica import buscar_comunicacoes


@pytest.mark.asyncio
async def test_http_nao_200_preenche_status_code_e_error(monkeypatch):
    def handler(request):
        return httpx.Response(500, json={"erro": "interno"})

    transport = httpx.MockTransport(handler)

    class _FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *a, **k):
            super().__init__(*a, transport=transport, **k)

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    stats: dict = {}
    resultado = await buscar_comunicacoes("123456", "CE", date(2026, 1, 1), date(2026, 7, 1), stats=stats)

    assert resultado == []
    assert stats.get("ok") is None  # nunca setado — não houve 200
    assert stats["status_code"] == 500
    assert "500" in stats["error"]


@pytest.mark.asyncio
async def test_excecao_de_rede_preenche_error(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("Connection refused")

    transport = httpx.MockTransport(handler)

    class _FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *a, **k):
            super().__init__(*a, transport=transport, **k)

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    stats: dict = {}
    resultado = await buscar_comunicacoes("123456", "CE", date(2026, 1, 1), date(2026, 7, 1), stats=stats)

    assert resultado == []
    assert stats.get("ok") is None
    assert "status_code" not in stats  # exceção antes de qualquer resposta HTTP
    assert "Connection refused" in stats["error"]


@pytest.mark.asyncio
async def test_sucesso_200_nao_seta_status_code_nem_error(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"items": []})

    transport = httpx.MockTransport(handler)

    class _FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *a, **k):
            super().__init__(*a, transport=transport, **k)

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    stats: dict = {}
    await buscar_comunicacoes("123456", "CE", date(2026, 1, 1), date(2026, 7, 1), stats=stats)

    assert stats.get("ok") is True
    assert "error" not in stats
    assert "status_code" not in stats
