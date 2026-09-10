"""Fase pós-260.10 (correção do catálogo de integrações .jus.br) — o
cliente HTTP de `PdpjFonte` (`_get_processo`/`testar`) trocou de
`httpx.AsyncClient` (sem nenhum User-Agent próprio, caindo no default
"python-httpx/x.x.x") para `curl_cffi.requests.AsyncSession` com
`impersonate="chrome124"` — mesma correção preventiva já aplicada em
`comunica.py`/`tribunais/base.py` contra bloqueio por fingerprint TLS.

Não havia NENHUM teste cobrindo a construção do client HTTP dentro deste
arquivo antes desta fase (os testes existentes de `PdpjFonte` mockam num
nível mais alto — `_get_processo` inteiro, ou o `CircuitBreaker`). Fecha
essa lacuna: prova nos dois sentidos — reverter pra `httpx.AsyncClient`
sem `impersonate` faz estes testes falharem (`AttributeError`/assert)."""
import pytest

import app.integrations.fontes.pdpj_fonte as pdpj_mod
from app.integrations.fontes.pdpj_fonte import PdpjFonte


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}

    def json(self):
        return self._json_data


class _FakeAsyncSession:
    """Fake curl_cffi.requests.AsyncSession — captura os kwargs de
    construção (timeout/impersonate) e devolve uma resposta roteirizada."""

    def __init__(self, *, response=None, captured=None, **kwargs):
        self._response = response
        self._captured = captured if captured is not None else {}
        self._captured["session_kwargs"] = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        self._captured["url"] = url
        self._captured["get_kwargs"] = kwargs
        return self._response


def _patch_session(monkeypatch, *, response=None):
    captured: dict = {}

    def _factory(*a, **kwargs):
        return _FakeAsyncSession(response=response, captured=captured, **kwargs)

    monkeypatch.setattr(pdpj_mod, "AsyncSession", _factory)
    return captured


@pytest.mark.asyncio
async def test_get_processo_usa_tls_impersonation(monkeypatch):
    captured = _patch_session(
        monkeypatch, response=_FakeResponse(200, json_data={"numeroProcesso": "123"})
    )
    fonte = PdpjFonte(token="tok-abc")

    resultado = await fonte._get_processo("0001234-56.2026.8.06.0100")

    assert resultado == {"numeroProcesso": "123"}
    assert captured["session_kwargs"]["impersonate"] == "chrome124"
    # Authorization/Accept continuam por chamada (específicos do PDPJ),
    # não em conflito com o impersonate.
    headers = captured["get_kwargs"]["headers"]
    assert headers["Authorization"] == "Bearer tok-abc"


@pytest.mark.asyncio
async def test_testar_usa_tls_impersonation(monkeypatch):
    captured = _patch_session(monkeypatch, response=_FakeResponse(200))
    fonte = PdpjFonte(token="tok-abc")

    ok, msg = await fonte.testar()

    assert ok is True
    assert captured["session_kwargs"]["impersonate"] == "chrome124"
