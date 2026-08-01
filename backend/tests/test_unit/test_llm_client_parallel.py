"""Fase 137.5 — comparação/consenso: `call_llm_parallel()` chama N configs
concorrentemente (sem contextvar, credenciais explícitas por chamada). Cada
`_call_with_config` nunca propaga exceção — 1 config falhando não derruba
as outras. Mesmos fakes de SDK de `test_llm_client_fallback.py`."""
import anthropic
import httpx
import openai
import pytest

import app.integrations.llm_client as llm_client

_REQ = httpx.Request("POST", "https://example.invalid/v1")
_RESP_AUTH = httpx.Response(status_code=401, request=_REQ)


class _FakeUsage:
    def __init__(self, input_tokens=10, output_tokens=20):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.prompt_tokens = input_tokens
        self.completion_tokens = output_tokens


class _FakeAnthropicResponse:
    def __init__(self, text="ok-anthropic"):
        self.content = [type("Block", (), {"text": text})()]
        self.usage = _FakeUsage()
        self.stop_reason = "end_turn"


class _FakeAnthropicMessages:
    def __init__(self, fails=False):
        self.calls = 0
        self.fails = fails

    async def create(self, **kwargs):
        self.calls += 1
        if self.fails:
            raise anthropic.AuthenticationError(message="unauthorized", response=_RESP_AUTH, body=None)
        return _FakeAnthropicResponse()


class _FakeAnthropicClient:
    def __init__(self, fails=False):
        self.messages = _FakeAnthropicMessages(fails=fails)


class _FakeOpenAIChoice:
    def __init__(self, content="ok-openai-compat"):
        self.message = type("Msg", (), {"content": content})()
        self.finish_reason = "stop"


class _FakeOpenAIResponse:
    def __init__(self, content="ok-openai-compat"):
        self.choices = [_FakeOpenAIChoice(content)]
        self.usage = _FakeUsage()


class _FakeOpenAICompletions:
    def __init__(self, fails=False):
        self.calls = 0
        self.fails = fails

    async def create(self, **kwargs):
        self.calls += 1
        if self.fails:
            raise openai.AuthenticationError(message="unauthorized", response=_RESP_AUTH, body=None)
        return _FakeOpenAIResponse()


class _FakeOpenAIClient:
    def __init__(self, fails=False):
        self.chat = type("Chat", (), {"completions": _FakeOpenAICompletions(fails=fails)})()


@pytest.mark.asyncio
async def test_call_llm_parallel_chama_n_configs_concorrentemente(monkeypatch):
    anthropic_client = _FakeAnthropicClient()
    openai_client = _FakeOpenAIClient()
    monkeypatch.setattr(llm_client, "_get_anthropic", lambda api_key: anthropic_client)
    monkeypatch.setattr(llm_client, "_get_openai_compatible", lambda base_url, api_key: openai_client)

    configs = [
        {"provider": "anthropic", "api_key": "k1", "model": "claude-sonnet-5", "base_url": None},
        {"provider": "deepseek", "api_key": "k2", "model": "deepseek-chat", "base_url": None},
    ]
    resultados = await llm_client.call_llm_parallel(configs, messages=[{"role": "user", "content": "oi"}])

    assert len(resultados) == 2
    assert resultados[0]["provider"] == "anthropic"
    assert resultados[0]["content"] == "ok-anthropic"
    assert resultados[0]["error"] is None
    assert resultados[1]["provider"] == "deepseek"
    assert resultados[1]["content"] == "ok-openai-compat"
    assert resultados[1]["error"] is None
    assert anthropic_client.messages.calls == 1
    assert openai_client.chat.completions.calls == 1


@pytest.mark.asyncio
async def test_call_llm_parallel_1_config_falhando_nao_derruba_as_outras(monkeypatch):
    anthropic_client_com_falha = _FakeAnthropicClient(fails=True)
    openai_client_ok = _FakeOpenAIClient()

    def _fake_get_anthropic(api_key):
        return anthropic_client_com_falha

    def _fake_get_openai_compatible(base_url, api_key):
        return openai_client_ok

    monkeypatch.setattr(llm_client, "_get_anthropic", _fake_get_anthropic)
    monkeypatch.setattr(llm_client, "_get_openai_compatible", _fake_get_openai_compatible)

    configs = [
        {"provider": "anthropic", "api_key": "chave-invalida", "model": "claude-sonnet-5", "base_url": None},
        {"provider": "deepseek", "api_key": "k2", "model": "deepseek-chat", "base_url": None},
    ]
    resultados = await llm_client.call_llm_parallel(configs, messages=[{"role": "user", "content": "oi"}])

    assert resultados[0]["error"] is not None
    assert resultados[0]["content"] is None
    assert resultados[1]["error"] is None
    assert resultados[1]["content"] == "ok-openai-compat"  # não afetada pela falha da 1ª


@pytest.mark.asyncio
async def test_call_with_config_devolve_latencia_e_custo(monkeypatch):
    monkeypatch.setattr(llm_client, "_get_anthropic", lambda api_key: _FakeAnthropicClient())

    resultado = await llm_client._call_with_config(
        {"provider": "anthropic", "api_key": "k1", "model": "claude-sonnet-5", "base_url": None},
        messages=[{"role": "user", "content": "oi"}],
    )

    assert resultado["latency_ms"] >= 0
    assert resultado["cost_usd"] >= 0
    assert resultado["input_tokens"] == 10
    assert resultado["output_tokens"] == 20


@pytest.mark.asyncio
async def test_call_llm_parallel_preserva_a_ordem_recebida(monkeypatch):
    monkeypatch.setattr(llm_client, "_get_anthropic", lambda api_key: _FakeAnthropicClient())
    monkeypatch.setattr(llm_client, "_get_openai_compatible", lambda base_url, api_key: _FakeOpenAIClient())

    configs = [
        {"provider": "deepseek", "api_key": "k1", "model": "deepseek-chat", "base_url": None},
        {"provider": "anthropic", "api_key": "k2", "model": "claude-sonnet-5", "base_url": None},
        {"provider": "openrouter", "api_key": "k3", "model": "openai/gpt-4.1", "base_url": None},
    ]
    resultados = await llm_client.call_llm_parallel(configs, messages=[{"role": "user", "content": "oi"}])

    assert [r["provider"] for r in resultados] == ["deepseek", "anthropic", "openrouter"]
