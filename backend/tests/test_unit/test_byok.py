"""Fase 137.1 — user_ai_creds() passa a resolver via AIProviderConfig (múltiplas
IAs por usuário), com fallback pras 4 colunas antigas do User quando não há
nenhuma config nova cadastrada (zero regressão pra quem não migrou)."""
import uuid
import pytest

import app.integrations.byok as byok_mod
from app.integrations.llm_client import ai_creds_ctx


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    """Devolve os resultados na ORDEM em que `session.execute()` é chamado."""
    def __init__(self, *results):
        self._results = list(results)
        self._i = 0

    async def execute(self, stmt):
        r = self._results[self._i]
        self._i += 1
        return r


class _FakeConfig:
    def __init__(self, provider="anthropic", credentials_enc="tok", model="claude-sonnet-5",
                 base_url=None, auth_method="api_key"):
        self.id = uuid.uuid4()
        self.provider = provider
        self.credentials_enc = credentials_enc
        self.model = model
        self.base_url = base_url
        self.auth_method = auth_method


class _FakeUser:
    def __init__(self, ai_enabled=True, ai_api_key_enc="tok", ai_provider="anthropic", ai_model="claude-sonnet-5"):
        self.ai_enabled = ai_enabled
        self.ai_api_key_enc = ai_api_key_enc
        self.ai_provider = ai_provider
        self.ai_model = ai_model


class _FakeOverride:
    def __init__(self, model):
        self.model = model


@pytest.mark.asyncio
async def test_usa_ai_provider_config_quando_existe(monkeypatch):
    import app.core.crypto as crypto_mod
    monkeypatch.setattr(crypto_mod, "decrypt", lambda tok: '{"api_key": "sk-config-123"}')

    config = _FakeConfig(provider="openrouter", base_url=None, model="openai/gpt-4.1")
    session = _FakeSession(_ScalarResult(config))  # 1 chamada: só a config (sem task_type)

    async with byok_mod.user_ai_creds(session, uuid.uuid4()):
        creds = ai_creds_ctx.get()
        assert creds == {"provider": "openrouter", "api_key": "sk-config-123", "model": "openai/gpt-4.1", "base_url": None}

    assert ai_creds_ctx.get() is None  # resetado ao sair do context manager


@pytest.mark.asyncio
async def test_config_com_auth_method_none_nao_exige_chave(monkeypatch):
    """Ollama: auth_method='none', sem credentials_enc — deve ativar mesmo sem chave."""
    config = _FakeConfig(provider="ollama", credentials_enc=None, auth_method="none",
                          base_url="http://localhost:11434/v1", model="llama3.1")
    session = _FakeSession(_ScalarResult(config))

    async with byok_mod.user_ai_creds(session, uuid.uuid4()):
        creds = ai_creds_ctx.get()
        assert creds["provider"] == "ollama"
        assert creds["api_key"] == ""
        assert creds["base_url"] == "http://localhost:11434/v1"


@pytest.mark.asyncio
async def test_task_type_aplica_override_sobre_config_nova(monkeypatch):
    import app.core.crypto as crypto_mod
    monkeypatch.setattr(crypto_mod, "decrypt", lambda tok: '{"api_key": "sk-1"}')

    config = _FakeConfig(model="claude-sonnet-5")
    override = _FakeOverride(model="claude-opus-4-8")
    session = _FakeSession(_ScalarResult(config), _ScalarResult(override))  # config, depois override

    async with byok_mod.user_ai_creds(session, uuid.uuid4(), task_type="generate_petition"):
        assert ai_creds_ctx.get()["model"] == "claude-opus-4-8"


@pytest.mark.asyncio
async def test_sem_ai_provider_config_cai_no_fallback_legado(monkeypatch):
    import app.core.crypto as crypto_mod
    monkeypatch.setattr(crypto_mod, "decrypt", lambda tok: "chave-legada")

    user = _FakeUser(ai_enabled=True, ai_api_key_enc="tok", ai_provider="gemini", ai_model="gemini-2.5-flash")
    session = _FakeSession(_ScalarResult(None), _ScalarResult(user))  # sem config → busca User

    async with byok_mod.user_ai_creds(session, uuid.uuid4()):
        creds = ai_creds_ctx.get()
        assert creds == {"provider": "gemini", "api_key": "chave-legada", "model": "gemini-2.5-flash", "base_url": None}


@pytest.mark.asyncio
async def test_sem_config_e_sem_byok_legado_e_no_op(monkeypatch):
    user = _FakeUser(ai_enabled=False)
    session = _FakeSession(_ScalarResult(None), _ScalarResult(user))

    async with byok_mod.user_ai_creds(session, uuid.uuid4()):
        assert ai_creds_ctx.get() is None


@pytest.mark.asyncio
async def test_config_indecifravel_nao_quebra_e_nao_ativa(monkeypatch):
    import app.core.crypto as crypto_mod
    monkeypatch.setattr(crypto_mod, "decrypt", lambda tok: None)  # ENCRYPTION_KEY mudou

    config = _FakeConfig()
    session = _FakeSession(_ScalarResult(config))

    async with byok_mod.user_ai_creds(session, uuid.uuid4()):
        assert ai_creds_ctx.get() is None  # fail-soft, sem exceção
