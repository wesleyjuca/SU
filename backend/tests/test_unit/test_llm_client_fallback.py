"""Fase 137.3 — fallback automático de `call_llm` entre as IAs do usuário
(via `ai_fallback_ctx`, montado por `byok.user_ai_creds()`) quando a config
ativa falha de um jeito recuperável (rede/timeout/rate-limit/5xx/auth).
`call_llm_stream` fica fora de escopo — não testado aqui (comportamento
inalterado, ver `test_llm_client_retry.py`)."""
import anthropic
import httpx
import openai
import pytest

import app.integrations.llm_client as llm_client

_REQ = httpx.Request("POST", "https://example.invalid/v1")
_RESP_ERROR = httpx.Response(status_code=429, request=_REQ)
_RESP_AUTH = httpx.Response(status_code=401, request=_REQ)


def _make_error(error_cls):
    if error_cls in (anthropic.APIConnectionError, openai.APIConnectionError):
        return error_cls(request=_REQ)
    if error_cls in (anthropic.APITimeoutError, openai.APITimeoutError):
        return error_cls(request=_REQ)
    if error_cls in (anthropic.AuthenticationError, openai.AuthenticationError):
        return error_cls(message="unauthorized", response=_RESP_AUTH, body=None)
    return error_cls(message="transient", response=_RESP_ERROR, body=None)


class _FakeUsage:
    def __init__(self, input_tokens=10, output_tokens=20):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.prompt_tokens = input_tokens
        self.completion_tokens = output_tokens


class _FakeAnthropicResponse:
    def __init__(self, text="ok-anthropic", stop_reason="end_turn"):
        self.content = [type("Block", (), {"text": text})()]
        self.usage = _FakeUsage()
        self.stop_reason = stop_reason


class _FakeAnthropicMessages:
    def __init__(self, always_fails=False, error_cls=None):
        self.calls = 0
        self.always_fails = always_fails
        self.error_cls = error_cls or anthropic.APIConnectionError

    async def create(self, **kwargs):
        self.calls += 1
        if self.always_fails:
            raise _make_error(self.error_cls)
        return _FakeAnthropicResponse()


class _FakeAnthropicClient:
    def __init__(self, **kw):
        self.messages = _FakeAnthropicMessages(**kw)


class _FakeOpenAIChoice:
    def __init__(self, content="ok-openai-compat", finish_reason="stop"):
        self.message = type("Msg", (), {"content": content})()
        self.finish_reason = finish_reason


class _FakeOpenAIResponse:
    def __init__(self, content="ok-openai-compat", finish_reason="stop"):
        self.choices = [_FakeOpenAIChoice(content, finish_reason)]
        self.usage = _FakeUsage()


class _FakeOpenAICompletions:
    def __init__(self, always_fails=False, error_cls=None):
        self.calls = 0
        self.always_fails = always_fails
        self.error_cls = error_cls or openai.APIConnectionError

    async def create(self, **kwargs):
        self.calls += 1
        if self.always_fails:
            raise _make_error(self.error_cls)
        return _FakeOpenAIResponse()


class _FakeOpenAIClient:
    def __init__(self, **kw):
        self.chat = type("Chat", (), {"completions": _FakeOpenAICompletions(**kw)})()


@pytest.fixture(autouse=True)
def _reset_ai_ctx():
    """Contextvars são globais no processo — limpa antes/depois de cada teste
    pra não vazar estado pra outros arquivos de teste rodando na mesma sessão."""
    creds_token = llm_client.ai_creds_ctx.set(None)
    fallback_token = llm_client.ai_fallback_ctx.set(None)
    yield
    llm_client.ai_creds_ctx.reset(creds_token)
    llm_client.ai_fallback_ctx.reset(fallback_token)


@pytest.mark.asyncio
async def test_call_llm_cai_pra_proxima_config_em_erro_retryable(monkeypatch):
    llm_client.ai_creds_ctx.set({"provider": "anthropic", "api_key": "key1", "model": "claude-sonnet-5", "base_url": None})
    llm_client.ai_fallback_ctx.set([
        {"provider": "gemini", "api_key": "key2", "model": "gemini-2.5-flash", "base_url": None},
    ])

    anthropic_client = _FakeAnthropicClient(always_fails=True)  # esgota o retry interno (2x) e propaga
    openai_client = _FakeOpenAIClient(always_fails=False)
    monkeypatch.setattr(llm_client, "_get_anthropic", lambda api_key: anthropic_client)
    monkeypatch.setattr(llm_client, "_get_openai_compatible", lambda base_url, api_key: openai_client)

    content, in_t, out_t, cost = await llm_client.call_llm(messages=[{"role": "user", "content": "oi"}])

    assert content == "ok-openai-compat"
    assert anthropic_client.messages.calls == 2  # stop_after_attempt(2) esgotado
    assert openai_client.chat.completions.calls == 1  # 1ª tentativa da config de fallback já funcionou


@pytest.mark.asyncio
async def test_call_llm_cai_pra_fallback_em_erro_de_auth(monkeypatch):
    """Auth error na config ativa NÃO é retryable intra-provedor (insistir na
    mesma chave não adianta), mas DEVE disparar fallback pra outra config."""
    llm_client.ai_creds_ctx.set({"provider": "anthropic", "api_key": "chave-revogada", "model": "claude-sonnet-5", "base_url": None})
    llm_client.ai_fallback_ctx.set([
        {"provider": "gemini", "api_key": "key2", "model": "gemini-2.5-flash", "base_url": None},
    ])

    anthropic_client = _FakeAnthropicClient(always_fails=True, error_cls=anthropic.AuthenticationError)
    openai_client = _FakeOpenAIClient(always_fails=False)
    monkeypatch.setattr(llm_client, "_get_anthropic", lambda api_key: anthropic_client)
    monkeypatch.setattr(llm_client, "_get_openai_compatible", lambda base_url, api_key: openai_client)

    content, *_ = await llm_client.call_llm(messages=[{"role": "user", "content": "oi"}])

    assert content == "ok-openai-compat"
    assert anthropic_client.messages.calls == 1  # auth error não retenta no MESMO provider


@pytest.mark.asyncio
async def test_call_llm_nao_cai_pra_fallback_em_erro_de_validacao(monkeypatch):
    """BadRequestError (formato de request inválido) não está no conjunto de
    fallback — não faz sentido tentar outra IA pra um payload malformado."""
    llm_client.ai_creds_ctx.set({"provider": "anthropic", "api_key": "key1", "model": "claude-sonnet-5", "base_url": None})
    llm_client.ai_fallback_ctx.set([
        {"provider": "gemini", "api_key": "key2", "model": "gemini-2.5-flash", "base_url": None},
    ])

    anthropic_client = _FakeAnthropicClient(always_fails=True, error_cls=anthropic.BadRequestError)
    openai_client = _FakeOpenAIClient(always_fails=False)
    monkeypatch.setattr(llm_client, "_get_anthropic", lambda api_key: anthropic_client)
    monkeypatch.setattr(llm_client, "_get_openai_compatible", lambda base_url, api_key: openai_client)

    with pytest.raises(anthropic.BadRequestError):
        await llm_client.call_llm(messages=[{"role": "user", "content": "oi"}])

    assert anthropic_client.messages.calls == 1
    assert openai_client.chat.completions.calls == 0  # fallback nunca chamado


@pytest.mark.asyncio
async def test_call_llm_cadeia_esgotada_relanca_excecao_da_ultima_config(monkeypatch):
    llm_client.ai_creds_ctx.set({"provider": "anthropic", "api_key": "key1", "model": "claude-sonnet-5", "base_url": None})
    llm_client.ai_fallback_ctx.set([
        {"provider": "gemini", "api_key": "key2", "model": "gemini-2.5-flash", "base_url": None},
    ])

    anthropic_client = _FakeAnthropicClient(always_fails=True)
    openai_client = _FakeOpenAIClient(always_fails=True)
    monkeypatch.setattr(llm_client, "_get_anthropic", lambda api_key: anthropic_client)
    monkeypatch.setattr(llm_client, "_get_openai_compatible", lambda base_url, api_key: openai_client)

    with pytest.raises(openai.APIConnectionError):
        await llm_client.call_llm(messages=[{"role": "user", "content": "oi"}])

    assert anthropic_client.messages.calls == 2
    assert openai_client.chat.completions.calls == 2


@pytest.mark.asyncio
async def test_call_llm_sem_fallback_configurado_comportamento_original(monkeypatch):
    """Sem `ai_fallback_ctx` (usuário com só 1 IA, ou chamada fora do BYOK) —
    zero mudança de comportamento em relação a antes da Fase 137.3."""
    llm_client.ai_creds_ctx.set({"provider": "anthropic", "api_key": "key1", "model": "claude-sonnet-5", "base_url": None})

    anthropic_client = _FakeAnthropicClient(always_fails=True)
    monkeypatch.setattr(llm_client, "_get_anthropic", lambda api_key: anthropic_client)

    with pytest.raises(anthropic.APIConnectionError):
        await llm_client.call_llm(messages=[{"role": "user", "content": "oi"}])

    assert anthropic_client.messages.calls == 2


@pytest.mark.asyncio
async def test_call_llm_config_ollama_com_api_key_vazia_nao_cai_no_sistema(monkeypatch):
    """Bug adjacente corrigido nesta fase: `creds.get("api_key")` truthy-check
    tratava uma config Ollama (`api_key=""` de propósito) como "sem BYOK" e
    caía silenciosamente pro provider do sistema."""
    llm_client.ai_creds_ctx.set({"provider": "ollama", "api_key": "", "model": "llama3.1", "base_url": "http://localhost:11434/v1"})

    captured = {}

    def _fake_get_openai_compatible(base_url, api_key):
        captured["base_url"] = base_url
        captured["api_key"] = api_key
        return _FakeOpenAIClient(always_fails=False)

    monkeypatch.setattr(llm_client, "_get_openai_compatible", _fake_get_openai_compatible)
    monkeypatch.setattr(llm_client.settings, "ANTHROPIC_API_KEY", "chave-do-sistema-nunca-deveria-ser-usada")

    content, *_ = await llm_client.call_llm(messages=[{"role": "user", "content": "oi"}])

    assert content == "ok-openai-compat"
    assert captured["base_url"] == "http://localhost:11434/v1"  # usou a config Ollama, não o sistema
