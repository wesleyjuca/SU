"""Fase 137.7 — `registrar_chamada_ia` (app/services/ai_monitoring.py):
no-op sem `config_id`, e fail-soft (nunca lança) mesmo se a sessão de DB
quebrar. Testa só a função isolada — a integração com `call_llm`/
`_call_with_config` já é coberta por `test_llm_client_fallback.py` e
`test_llm_client_parallel.py` (que não afirmam nada sobre logging), então
aqui também cobrimos que `call_llm` chama `registrar_chamada_ia` com os
argumentos certos via monkeypatch direto no módulo."""
import uuid
import pytest


@pytest.mark.asyncio
async def test_registrar_chamada_ia_noop_sem_config_id():
    from app.services.ai_monitoring import registrar_chamada_ia

    # Não deve tentar abrir sessão nenhuma — se tentasse, quebraria (sem DB
    # real configurado neste teste unitário).
    await registrar_chamada_ia(
        config_id=None, provider="anthropic", model="claude-sonnet-5",
        success=True, error=None, input_tokens=10, output_tokens=20,
        cost_usd=0.001, latency_ms=100,
    )


@pytest.mark.asyncio
async def test_registrar_chamada_ia_fail_soft_nunca_lanca(monkeypatch):
    import app.services.ai_monitoring as mod

    class _BoomSessionLocal:
        def __call__(self):
            raise RuntimeError("DB indisponível")

    monkeypatch.setattr(
        "app.db.base.AsyncSessionLocal", _BoomSessionLocal(), raising=True,
    )

    # Não deve propagar a exceção — é telemetria, nunca pode derrubar a
    # chamada de LLM real.
    await mod.registrar_chamada_ia(
        config_id=str(uuid.uuid4()), provider="anthropic", model="claude-sonnet-5",
        success=False, error="timeout", input_tokens=0, output_tokens=0,
        cost_usd=0.0, latency_ms=50,
    )


@pytest.mark.asyncio
async def test_call_llm_loga_sucesso_com_config_id(monkeypatch):
    import app.integrations.llm_client as llm_client

    creds_token = llm_client.ai_creds_ctx.set({
        "provider": "anthropic", "api_key": "key1", "model": "claude-sonnet-5",
        "base_url": None, "config_id": "cfg-123",
    })
    fallback_token = llm_client.ai_fallback_ctx.set(None)
    try:
        class _FakeUsage:
            input_tokens = 5
            output_tokens = 7

        class _FakeResp:
            content = [type("Block", (), {"text": "ok"})()]
            usage = _FakeUsage()
            stop_reason = "end_turn"

        class _FakeMessages:
            async def create(self, **kwargs):
                return _FakeResp()

        class _FakeClient:
            def __init__(self):
                self.messages = _FakeMessages()

        monkeypatch.setattr(llm_client, "_get_anthropic", lambda api_key: _FakeClient())

        chamadas = []

        async def _fake_registrar(config_id, provider, model, success, error, in_t, out_t, cost, latency_ms):
            chamadas.append((config_id, provider, model, success, error))

        monkeypatch.setattr("app.services.ai_monitoring.registrar_chamada_ia", _fake_registrar)

        content, *_ = await llm_client.call_llm(messages=[{"role": "user", "content": "oi"}])

        assert content == "ok"
        assert len(chamadas) == 1
        assert chamadas[0] == ("cfg-123", "anthropic", "claude-sonnet-5", True, None)
    finally:
        llm_client.ai_creds_ctx.reset(creds_token)
        llm_client.ai_fallback_ctx.reset(fallback_token)


@pytest.mark.asyncio
async def test_call_llm_loga_falha_que_dispara_fallback(monkeypatch):
    import anthropic
    import httpx
    import app.integrations.llm_client as llm_client

    creds_token = llm_client.ai_creds_ctx.set({
        "provider": "anthropic", "api_key": "chave-revogada", "model": "claude-sonnet-5",
        "base_url": None, "config_id": "cfg-primaria",
    })
    fallback_token = llm_client.ai_fallback_ctx.set([
        {"provider": "gemini", "api_key": "key2", "model": "gemini-2.5-flash",
         "base_url": None, "config_id": "cfg-fallback"},
    ])
    try:
        req = httpx.Request("POST", "https://example.invalid/v1")
        resp = httpx.Response(status_code=401, request=req)

        class _FakeMessages:
            async def create(self, **kwargs):
                raise anthropic.AuthenticationError(message="unauthorized", response=resp, body=None)

        class _FakeAnthropicClient:
            def __init__(self):
                self.messages = _FakeMessages()

        class _FakeUsage:
            prompt_tokens = 3
            completion_tokens = 4

        class _FakeOpenAIChoice:
            message = type("Msg", (), {"content": "ok-fallback"})()
            finish_reason = "stop"

        class _FakeOpenAIResponse:
            choices = [_FakeOpenAIChoice()]
            usage = _FakeUsage()

        class _FakeOpenAICompletions:
            async def create(self, **kwargs):
                return _FakeOpenAIResponse()

        class _FakeOpenAIClient:
            def __init__(self):
                self.chat = type("Chat", (), {"completions": _FakeOpenAICompletions()})()

        monkeypatch.setattr(llm_client, "_get_anthropic", lambda api_key: _FakeAnthropicClient())
        monkeypatch.setattr(llm_client, "_get_openai_compatible", lambda base_url, api_key: _FakeOpenAIClient())

        chamadas = []

        async def _fake_registrar(config_id, provider, model, success, error, in_t, out_t, cost, latency_ms):
            chamadas.append((config_id, provider, success))

        monkeypatch.setattr("app.services.ai_monitoring.registrar_chamada_ia", _fake_registrar)

        content, *_ = await llm_client.call_llm(messages=[{"role": "user", "content": "oi"}])

        assert content == "ok-fallback"
        assert len(chamadas) == 2
        assert chamadas[0] == ("cfg-primaria", "anthropic", False)
        assert chamadas[1] == ("cfg-fallback", "gemini", True)
    finally:
        llm_client.ai_creds_ctx.reset(creds_token)
        llm_client.ai_fallback_ctx.reset(fallback_token)
