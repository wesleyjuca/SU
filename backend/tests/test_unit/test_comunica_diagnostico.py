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
async def test_http_403_preenche_status_code_e_error(monkeypatch):
    """Achado real em produção: a Comunica/DJEN devolveu 403 — a mensagem
    honesta da Fase 114 ("fonte não respondeu... verifique egress") saiu
    correta, mas a causa real (403, não falta de rede) só ficava visível no
    stats. Confirma o mesmo comportamento de captura de status_code/error
    para 403 especificamente."""
    def handler(request):
        return httpx.Response(403, text="Forbidden")

    transport = httpx.MockTransport(handler)

    class _FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *a, **k):
            super().__init__(*a, transport=transport, **k)

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    stats: dict = {}
    resultado = await buscar_comunicacoes("123456", "CE", date(2026, 1, 1), date(2026, 7, 1), stats=stats)

    assert resultado == []
    assert stats["status_code"] == 403
    assert "403" in stats["error"]


@pytest.mark.asyncio
async def test_requisicao_envia_user_agent_identificado(monkeypatch):
    """Fix do 403 real em produção: httpx sem headers manda um User-Agent
    genérico (python-httpx/x.x), que APIs públicas com proteção anti-bot
    (como a Comunica/DJEN) costumam rejeitar. Confirma que o cliente agora
    identifica a origem da requisição, mesmo padrão já usado em
    tribunais/base.py."""
    capturado = {}

    def handler(request):
        capturado["user_agent"] = request.headers.get("user-agent")
        capturado["accept"] = request.headers.get("accept")
        return httpx.Response(200, json={"items": []})

    transport = httpx.MockTransport(handler)

    class _FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *a, **k):
            super().__init__(*a, transport=transport, **k)

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    await buscar_comunicacoes("123456", "CE", date(2026, 1, 1), date(2026, 7, 1))

    assert capturado["user_agent"] is not None
    assert "python-httpx" not in capturado["user_agent"].lower()
    assert "AFJ-Core" in capturado["user_agent"]
    assert capturado["accept"] == "application/json"


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
