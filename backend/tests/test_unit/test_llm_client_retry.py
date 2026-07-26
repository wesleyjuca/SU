"""Fase 110 — retry raso (tenacity) nas chamadas-folha de LLM: absorve blips
transientes de rede/rate-limit sem compor com o retry mais grosso de
BaseAgent.run(). Nunca retenta erro de validação/auth."""
import anthropic
import httpx
import openai
import pytest

import app.integrations.llm_client as llm_client

_REQ = httpx.Request("POST", "https://example.invalid/v1")
_RESP_ERROR = httpx.Response(status_code=429, request=_REQ)


def _make_error(error_cls):
    """Instancia a exceção do SDK com um httpx.Request/Response reais —
    APIStatusError acessa response.request internamente, response=None quebra."""
    if error_cls in (anthropic.APIConnectionError, openai.APIConnectionError):
        return error_cls(request=_REQ)
    if error_cls in (anthropic.APITimeoutError, openai.APITimeoutError):
        return error_cls(request=_REQ)
    return error_cls(message="transient", response=_RESP_ERROR, body=None)


class _FakeUsage:
    def __init__(self, input_tokens=10, output_tokens=20):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.prompt_tokens = input_tokens
        self.completion_tokens = output_tokens


class _FakeAnthropicResponse:
    def __init__(self, text="ok"):
        self.content = [type("Block", (), {"text": text})()]
        self.usage = _FakeUsage()


class _FakeAnthropicMessages:
    def __init__(self, fails_then_succeeds=0, error_cls=None):
        self.calls = 0
        self.fails_then_succeeds = fails_then_succeeds
        self.error_cls = error_cls or anthropic.APIConnectionError

    async def create(self, **kwargs):
        self.calls += 1
        if self.calls <= self.fails_then_succeeds:
            raise _make_error(self.error_cls)
        return _FakeAnthropicResponse()


class _FakeAnthropicClient:
    def __init__(self, **kw):
        self.messages = _FakeAnthropicMessages(**kw)


class _FakeOpenAIChoice:
    def __init__(self, content="ok"):
        self.message = type("Msg", (), {"content": content})()


class _FakeOpenAIResponse:
    def __init__(self, content="ok"):
        self.choices = [_FakeOpenAIChoice(content)]
        self.usage = _FakeUsage()


class _FakeOpenAICompletions:
    def __init__(self, fails_then_succeeds=0, error_cls=None):
        self.calls = 0
        self.fails_then_succeeds = fails_then_succeeds
        self.error_cls = error_cls or openai.APIConnectionError

    async def create(self, **kwargs):
        self.calls += 1
        if self.calls <= self.fails_then_succeeds:
            raise _make_error(self.error_cls)
        return _FakeOpenAIResponse()


class _FakeOpenAIClient:
    def __init__(self, **kw):
        self.chat = type("Chat", (), {"completions": _FakeOpenAICompletions(**kw)})()


@pytest.mark.asyncio
async def test_call_anthropic_retenta_uma_vez_em_erro_transiente(monkeypatch):
    fake_client = _FakeAnthropicClient(fails_then_succeeds=1)
    monkeypatch.setattr(llm_client, "_get_anthropic", lambda api_key: fake_client)

    content, in_t, out_t = await llm_client._call_anthropic(
        "key", [{"role": "user", "content": "oi"}], "", "claude-sonnet-5", 100, 0.1
    )
    assert content == "ok"
    assert fake_client.messages.calls == 2  # 1 falha + 1 sucesso


@pytest.mark.asyncio
async def test_call_anthropic_propaga_apos_esgotar_retries(monkeypatch):
    fake_client = _FakeAnthropicClient(fails_then_succeeds=5)  # sempre falha
    monkeypatch.setattr(llm_client, "_get_anthropic", lambda api_key: fake_client)

    with pytest.raises(anthropic.APIConnectionError):
        await llm_client._call_anthropic(
            "key", [{"role": "user", "content": "oi"}], "", "claude-sonnet-5", 100, 0.1
        )
    assert fake_client.messages.calls == 2  # stop_after_attempt(2), nunca mais que isso


@pytest.mark.asyncio
async def test_call_anthropic_nao_retenta_erro_nao_transiente(monkeypatch):
    fake_client = _FakeAnthropicClient(fails_then_succeeds=5, error_cls=anthropic.BadRequestError)
    monkeypatch.setattr(llm_client, "_get_anthropic", lambda api_key: fake_client)

    with pytest.raises(anthropic.BadRequestError):
        await llm_client._call_anthropic(
            "key", [{"role": "user", "content": "oi"}], "", "claude-sonnet-5", 100, 0.1
        )
    assert fake_client.messages.calls == 1  # sem retry — falhou na 1ª


@pytest.mark.asyncio
async def test_call_gemini_retenta_uma_vez_em_erro_transiente(monkeypatch):
    fake_client = _FakeOpenAIClient(fails_then_succeeds=1)
    monkeypatch.setattr(llm_client, "_get_gemini", lambda api_key: fake_client)

    content, in_t, out_t = await llm_client._call_gemini(
        "key", [{"role": "user", "content": "oi"}], "", "gemini-2.5-flash", 100, 0.1
    )
    assert content == "ok"
    assert fake_client.chat.completions.calls == 2


@pytest.mark.asyncio
async def test_call_gemini_nao_retenta_erro_nao_transiente(monkeypatch):
    fake_client = _FakeOpenAIClient(fails_then_succeeds=5, error_cls=openai.AuthenticationError)
    monkeypatch.setattr(llm_client, "_get_gemini", lambda api_key: fake_client)

    with pytest.raises(openai.AuthenticationError):
        await llm_client._call_gemini(
            "key", [{"role": "user", "content": "oi"}], "", "gemini-2.5-flash", 100, 0.1
        )
    assert fake_client.chat.completions.calls == 1
