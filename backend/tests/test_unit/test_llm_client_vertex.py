"""Fase 195 — Google Vertex AI como provedor de IA (BYOK via conta de
serviço do projeto GCP do próprio escritório). Diferente dos demais
provedores (todos OpenAI-compatíveis), Vertex tem branch dedicado
(`_call_vertex_ai`) — não é SDK, é REST puro via httpx (token OAuth2 pelo
fluxo JWT Bearer + chamada generateContent), mesmo padrão das outras
integrações Google deste projeto (google_workspace.py)."""
import json
import time

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import app.integrations.llm_client as llm_client
from app.integrations.llm_client import _call_vertex_ai, _vertex_access_token, resolve_provider, call_llm

# Chave RSA real (só pra assinatura RS256 funcionar no teste) — não uma
# credencial de verdade, gerada em memória, nunca sai deste processo.
_TEST_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_TEST_PRIVATE_KEY_PEM = _TEST_RSA_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode()

_SA_JSON = json.dumps({
    "type": "service_account",
    "project_id": "afj-teste-123",
    "private_key_id": "abc123",
    "private_key": _TEST_PRIVATE_KEY_PEM,
    "client_email": "afj-vertex@afj-teste-123.iam.gserviceaccount.com",
})


class _FakeResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json = json_data
        self.text = json.dumps(json_data)

    def json(self):
        return self._json


class _FakeAsyncClient:
    def __init__(self, log, responses, **kwargs):
        self._log = log
        self._responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kwargs):
        self._log.append((url, kwargs))
        for marcador, resp in self._responses.items():
            if marcador in url:
                return resp
        raise AssertionError(f"URL inesperada: {url}")


def _patch_httpx(monkeypatch, responses):
    log = []
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(log, responses, **kw))
    return log


@pytest.fixture(autouse=True)
def _limpa_cache_de_token():
    llm_client._client_cache.clear()
    yield
    llm_client._client_cache.clear()


def test_resolve_provider_reconhece_vertex_ai():
    assert resolve_provider("vertex_ai") == "vertex_ai"


@pytest.mark.asyncio
async def test_call_vertex_ai_sucesso(monkeypatch):
    log = _patch_httpx(monkeypatch, {
        "oauth2.googleapis.com/token": _FakeResponse(200, {"access_token": "tok-123", "expires_in": 3600}),
        "generateContent": _FakeResponse(200, {
            "candidates": [{
                "content": {"parts": [{"text": "resposta do vertex"}]},
                "finishReason": "STOP",
            }],
            "usageMetadata": {"promptTokenCount": 15, "candidatesTokenCount": 8},
        }),
    })

    content, in_t, out_t, finish = await _call_vertex_ai(
        _SA_JSON, "us-central1", [{"role": "user", "content": "oi"}], "", "gemini-2.5-flash", 512, 0.3,
    )

    assert content == "resposta do vertex"
    assert (in_t, out_t) == (15, 8)
    assert finish == "STOP"
    assert any("afj-teste-123" in url and "us-central1" in url for url, _ in log)


@pytest.mark.asyncio
async def test_call_vertex_ai_usa_location_padrao_quando_omitida(monkeypatch):
    log = _patch_httpx(monkeypatch, {
        "oauth2.googleapis.com/token": _FakeResponse(200, {"access_token": "tok-123", "expires_in": 3600}),
        "generateContent": _FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": "x"}]}, "finishReason": "STOP"}]}),
    })

    await _call_vertex_ai(_SA_JSON, None, [{"role": "user", "content": "oi"}], "", "gemini-2.5-flash", 512, 0.3)

    assert any("us-central1-aiplatform.googleapis.com" in url for url, _ in log)


@pytest.mark.asyncio
async def test_call_vertex_ai_credencial_json_invalido():
    with pytest.raises(RuntimeError, match="Credencial do Vertex AI inválida"):
        await _call_vertex_ai("não é json", "us-central1", [{"role": "user", "content": "oi"}], "", "gemini-2.5-flash", 512, 0.3)


@pytest.mark.asyncio
async def test_call_vertex_ai_json_incompleto():
    incompleto = json.dumps({"type": "service_account", "project_id": "afj-teste-123"})  # sem client_email/private_key
    with pytest.raises(RuntimeError, match="incompleto"):
        await _call_vertex_ai(incompleto, "us-central1", [{"role": "user", "content": "oi"}], "", "gemini-2.5-flash", 512, 0.3)


@pytest.mark.asyncio
async def test_call_vertex_ai_erro_da_api_vira_runtime_error(monkeypatch):
    _patch_httpx(monkeypatch, {
        "oauth2.googleapis.com/token": _FakeResponse(200, {"access_token": "tok-123", "expires_in": 3600}),
        "generateContent": _FakeResponse(403, {"error": {"message": "Vertex AI API não habilitada no projeto"}}),
    })

    with pytest.raises(RuntimeError, match="Vertex AI recusou a chamada"):
        await _call_vertex_ai(_SA_JSON, "us-central1", [{"role": "user", "content": "oi"}], "", "gemini-2.5-flash", 512, 0.3)


@pytest.mark.asyncio
async def test_vertex_access_token_e_cacheado_entre_chamadas(monkeypatch):
    log = _patch_httpx(monkeypatch, {
        "oauth2.googleapis.com/token": _FakeResponse(200, {"access_token": "tok-cacheado", "expires_in": 3600}),
    })
    sa = json.loads(_SA_JSON)

    tok1 = await _vertex_access_token(sa)
    tok2 = await _vertex_access_token(sa)

    assert tok1 == tok2 == "tok-cacheado"
    chamadas_token = [u for u, _ in log if "oauth2.googleapis.com/token" in u]
    assert len(chamadas_token) == 1  # 2ª chamada usou o cache, não bateu na rede de novo


@pytest.mark.asyncio
async def test_vertex_access_token_expirado_busca_novo(monkeypatch):
    log = _patch_httpx(monkeypatch, {
        "oauth2.googleapis.com/token": _FakeResponse(200, {"access_token": "tok-novo", "expires_in": 3600}),
    })
    sa = json.loads(_SA_JSON)
    # Simula um token cacheado que já expirou (timestamp no passado).
    ck = ("vertex_token", sa.get("client_email"), sa.get("private_key_id"))
    llm_client._client_cache[ck] = ("tok-velho", time.time() - 10)

    tok = await _vertex_access_token(sa)

    assert tok == "tok-novo"
    assert len([u for u, _ in log if "token" in u]) == 1


@pytest.mark.asyncio
async def test_call_llm_dispatcha_para_vertex_ai(monkeypatch):
    async def _fake_call_vertex(service_account_json, location, messages, system, model, max_tokens, temperature):
        return "ok-vertex", 5, 10, "STOP"

    monkeypatch.setattr(llm_client, "_call_vertex_ai", _fake_call_vertex)

    async def _fake_registrar(*a, **k):
        pass
    monkeypatch.setattr("app.services.ai_monitoring.registrar_chamada_ia", _fake_registrar)

    token = llm_client.ai_creds_ctx.set({
        "provider": "vertex_ai", "api_key": _SA_JSON, "model": "gemini-2.5-flash", "base_url": "us-central1",
    })
    try:
        content, in_t, out_t, cost = await call_llm([{"role": "user", "content": "oi"}])
    finally:
        llm_client.ai_creds_ctx.reset(token)

    assert content == "ok-vertex"
    assert (in_t, out_t) == (5, 10)
