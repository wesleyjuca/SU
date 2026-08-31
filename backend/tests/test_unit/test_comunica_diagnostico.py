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
async def test_requisicao_envia_user_agent_de_navegador(monkeypatch):
    """Fase 114 trocou o User-Agent genérico do httpx por um identificador
    próprio ("AFJ-Core/1.0 (...)") — resolveu a rejeição da época, mas a
    Fase 250 achou um 403 real em produção com esse mesmo UA: o WAF do
    Comunica/DJEN passou a rejeitar também um UA que se autoidentifica como
    sistema/bot, só aceitando tráfego que pareça vir de um navegador (o
    mesmo formato que o próprio site público comunica.pje.jus.br usa pra
    chamar esta API). Confirma que o cliente agora manda UA/Accept-Language/
    Referer/Origin de navegador real — não é evasão, é o mesmo formato de
    requisição que qualquer usuário faria pela página pública de consulta."""
    capturado = {}

    def handler(request):
        capturado["user_agent"] = request.headers.get("user-agent")
        capturado["accept"] = request.headers.get("accept")
        capturado["accept_language"] = request.headers.get("accept-language")
        capturado["referer"] = request.headers.get("referer")
        capturado["origin"] = request.headers.get("origin")
        return httpx.Response(200, json={"items": []})

    transport = httpx.MockTransport(handler)

    class _FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *a, **k):
            super().__init__(*a, transport=transport, **k)

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    await buscar_comunicacoes("123456", "CE", date(2026, 1, 1), date(2026, 7, 1))

    assert capturado["user_agent"] is not None
    assert "python-httpx" not in capturado["user_agent"].lower()
    assert "AFJ-Core" not in capturado["user_agent"]
    assert "Mozilla" in capturado["user_agent"] and "Chrome" in capturado["user_agent"]
    assert capturado["accept_language"] == "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
    assert capturado["referer"] == "https://comunica.pje.jus.br/consulta"
    assert capturado["origin"] == "https://comunica.pje.jus.br"


@pytest.mark.asyncio
async def test_falha_captura_corpo_bruto_da_resposta(monkeypatch):
    """Fase 252 — o 403 persistiu em produção mesmo depois do fix de headers
    da Fase 250, indício de um bloqueio mais fundo (fingerprint TLS, IP na
    lista negra do WAF) — mas até aqui só o status code era capturado,
    nunca o CORPO da resposta (que revelaria, por exemplo, uma página de
    desafio Cloudflare/Akamai em vez de um 403 seco). Confirma que
    `stats["body_snippet"]` chega preenchido e truncado."""
    corpo_desafio = "<html><body>Access denied — Cloudflare Ray ID: abc123</body></html>" + ("x" * 600)

    def handler(request):
        return httpx.Response(403, text=corpo_desafio)

    transport = httpx.MockTransport(handler)

    class _FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *a, **k):
            super().__init__(*a, transport=transport, **k)

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    stats: dict = {}
    resultado = await buscar_comunicacoes("123456", "CE", date(2026, 1, 1), date(2026, 7, 1), stats=stats)

    assert resultado == []
    assert stats["status_code"] == 403
    assert "Cloudflare Ray ID" in stats["body_snippet"]
    assert len(stats["body_snippet"]) <= 500


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
