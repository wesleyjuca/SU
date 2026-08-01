"""Fase 137.1 — user_ai_creds() passa a resolver via AIProviderConfig (múltiplas
IAs por usuário), com fallback pras 4 colunas antigas do User quando não há
nenhuma config nova cadastrada (zero regressão pra quem não migrou).

Fase 137.3 — a mesma query agora traz TODAS as configs `enabled=True`
ordenadas (não só a padrão): a primeira decifrável vira `ai_creds_ctx`, as
demais viram a cadeia de fallback em `ai_fallback_ctx`."""
import uuid
import pytest

import app.integrations.byok as byok_mod
from app.integrations.llm_client import ai_creds_ctx, ai_fallback_ctx


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _RowsResult:
    """Simula o retorno de `.scalars().all()` — múltiplas linhas, na ordem
    em que a query as devolveria (ORDER BY já aplicado)."""
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        rows = self._rows

        class _S:
            def all(self):
                return rows
        return _S()


class _FakeSession:
    """Devolve os resultados na ORDEM em que `session.execute()` é chamado.
    `get_map` resolve `session.get(Model, id)` (usado pelo override com
    `provider_config_id` — Fase 137.4)."""
    def __init__(self, *results, get_map=None):
        self._results = list(results)
        self._i = 0
        self._get_map = get_map or {}

    async def execute(self, stmt):
        r = self._results[self._i]
        self._i += 1
        return r

    async def get(self, model, obj_id):
        return self._get_map.get((model, obj_id))


class _FakeConfig:
    def __init__(self, provider="anthropic", credentials_enc="tok", model="claude-sonnet-5",
                 base_url=None, auth_method="api_key", user_id=None, enabled=True):
        self.id = uuid.uuid4()
        self.provider = provider
        self.credentials_enc = credentials_enc
        self.model = model
        self.base_url = base_url
        self.auth_method = auth_method
        self.user_id = user_id
        self.enabled = enabled


class _FakeUser:
    def __init__(self, ai_enabled=True, ai_api_key_enc="tok", ai_provider="anthropic", ai_model="claude-sonnet-5"):
        self.ai_enabled = ai_enabled
        self.ai_api_key_enc = ai_api_key_enc
        self.ai_provider = ai_provider
        self.ai_model = ai_model


class _FakeOverride:
    def __init__(self, model=None, provider_config_id=None):
        self.model = model
        self.provider_config_id = provider_config_id


@pytest.mark.asyncio
async def test_usa_ai_provider_config_quando_existe(monkeypatch):
    import app.core.crypto as crypto_mod
    monkeypatch.setattr(crypto_mod, "decrypt", lambda tok: '{"api_key": "sk-config-123"}')

    config = _FakeConfig(provider="openrouter", base_url=None, model="openai/gpt-4.1")
    session = _FakeSession(_RowsResult([config]))  # 1 chamada: as configs (sem task_type)

    async with byok_mod.user_ai_creds(session, uuid.uuid4()):
        creds = ai_creds_ctx.get()
        assert creds == {"provider": "openrouter", "api_key": "sk-config-123", "model": "openai/gpt-4.1", "base_url": None}
        assert ai_fallback_ctx.get() is None  # só 1 config — sem cadeia

    assert ai_creds_ctx.get() is None  # resetado ao sair do context manager


@pytest.mark.asyncio
async def test_config_com_auth_method_none_nao_exige_chave(monkeypatch):
    """Ollama: auth_method='none', sem credentials_enc — deve ativar mesmo sem chave."""
    config = _FakeConfig(provider="ollama", credentials_enc=None, auth_method="none",
                          base_url="http://localhost:11434/v1", model="llama3.1")
    session = _FakeSession(_RowsResult([config]))

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
    session = _FakeSession(_RowsResult([config]), _ScalarResult(override))  # configs, depois override

    async with byok_mod.user_ai_creds(session, uuid.uuid4(), task_type="generate_petition"):
        assert ai_creds_ctx.get()["model"] == "claude-opus-4-8"


@pytest.mark.asyncio
async def test_sem_ai_provider_config_cai_no_fallback_legado(monkeypatch):
    import app.core.crypto as crypto_mod
    monkeypatch.setattr(crypto_mod, "decrypt", lambda tok: "chave-legada")

    user = _FakeUser(ai_enabled=True, ai_api_key_enc="tok", ai_provider="gemini", ai_model="gemini-2.5-flash")
    session = _FakeSession(_RowsResult([]), _ScalarResult(user))  # sem config → busca User

    async with byok_mod.user_ai_creds(session, uuid.uuid4()):
        creds = ai_creds_ctx.get()
        assert creds == {"provider": "gemini", "api_key": "chave-legada", "model": "gemini-2.5-flash", "base_url": None}
        assert ai_fallback_ctx.get() is None  # fallback legado nunca monta cadeia


@pytest.mark.asyncio
async def test_sem_config_e_sem_byok_legado_e_no_op(monkeypatch):
    user = _FakeUser(ai_enabled=False)
    session = _FakeSession(_RowsResult([]), _ScalarResult(user))

    async with byok_mod.user_ai_creds(session, uuid.uuid4()):
        assert ai_creds_ctx.get() is None


@pytest.mark.asyncio
async def test_config_indecifravel_cai_no_legado_e_nao_quebra(monkeypatch):
    """Única config existente veio indecifrável (ENCRYPTION_KEY mudou) — cai
    no mesmo caminho de "sem config nenhuma" (fail-soft); se o legado também
    não tiver nada usável, o resultado final é no-op, sem exceção."""
    import app.core.crypto as crypto_mod
    monkeypatch.setattr(crypto_mod, "decrypt", lambda tok: None)

    config = _FakeConfig()
    session = _FakeSession(_RowsResult([config]), _ScalarResult(None))  # config indecifrável, legado sem User

    async with byok_mod.user_ai_creds(session, uuid.uuid4()):
        assert ai_creds_ctx.get() is None  # fail-soft, sem exceção
        assert ai_fallback_ctx.get() is None


# ─── Fase 137.3 — cadeia de fallback ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_monta_cadeia_de_fallback_com_2_configs(monkeypatch):
    import app.core.crypto as crypto_mod
    monkeypatch.setattr(crypto_mod, "decrypt", lambda tok: '{"api_key": "sk-' + tok + '"}')

    primaria = _FakeConfig(provider="anthropic", credentials_enc="1", model="claude-sonnet-5")
    fallback = _FakeConfig(provider="gemini", credentials_enc="2", model="gemini-2.5-flash")
    session = _FakeSession(_RowsResult([primaria, fallback]))

    async with byok_mod.user_ai_creds(session, uuid.uuid4()):
        assert ai_creds_ctx.get()["provider"] == "anthropic"
        cadeia = ai_fallback_ctx.get()
        assert cadeia == [{"provider": "gemini", "api_key": "sk-2", "model": "gemini-2.5-flash", "base_url": None}]

    assert ai_creds_ctx.get() is None
    assert ai_fallback_ctx.get() is None  # resetado ao sair


@pytest.mark.asyncio
async def test_config_indecifravel_no_meio_da_cadeia_e_pulada(monkeypatch):
    """A 2ª config da lista está indecifrável (chave revogada/corrompida) —
    é pulada, a 3ª ainda entra na cadeia de fallback."""
    import app.core.crypto as crypto_mod

    def _decrypt(tok):
        if tok == "quebrada":
            return None
        return f'{{"api_key": "sk-{tok}"}}'
    monkeypatch.setattr(crypto_mod, "decrypt", _decrypt)

    c1 = _FakeConfig(provider="anthropic", credentials_enc="1")
    c2 = _FakeConfig(provider="openai", credentials_enc="quebrada")
    c3 = _FakeConfig(provider="openrouter", credentials_enc="3")
    session = _FakeSession(_RowsResult([c1, c2, c3]))

    async with byok_mod.user_ai_creds(session, uuid.uuid4()):
        assert ai_creds_ctx.get()["provider"] == "anthropic"
        cadeia = ai_fallback_ctx.get()
        assert len(cadeia) == 1
        assert cadeia[0]["provider"] == "openrouter"


@pytest.mark.asyncio
async def test_primaria_indecifravel_promove_proxima_config_como_padrao_efetiva(monkeypatch):
    """Se a config marcada padrão (1ª da lista ordenada) está indecifrável,
    a próxima decifrável assume como padrão EFETIVA desta chamada — melhor
    que desistir de vez e cair no provider do sistema."""
    import app.core.crypto as crypto_mod

    def _decrypt(tok):
        if tok == "quebrada":
            return None
        return f'{{"api_key": "sk-{tok}"}}'
    monkeypatch.setattr(crypto_mod, "decrypt", _decrypt)

    padrao_quebrada = _FakeConfig(provider="anthropic", credentials_enc="quebrada")
    segunda = _FakeConfig(provider="gemini", credentials_enc="2")
    session = _FakeSession(_RowsResult([padrao_quebrada, segunda]))

    async with byok_mod.user_ai_creds(session, uuid.uuid4()):
        creds = ai_creds_ctx.get()
        assert creds["provider"] == "gemini"
        assert creds["api_key"] == "sk-2"
        assert ai_fallback_ctx.get() is None  # não sobrou mais ninguém pra cadeia


# ─── Fase 137.4 — "ajuste por área" referencia uma IA inteira ────────────────

@pytest.mark.asyncio
async def test_override_com_provider_config_id_substitui_a_config_inteira(monkeypatch):
    from app.models.ai_config import AIProviderConfig
    import app.core.crypto as crypto_mod
    monkeypatch.setattr(crypto_mod, "decrypt", lambda tok: '{"api_key": "sk-' + tok + '"}')

    user_id = uuid.uuid4()
    padrao = _FakeConfig(provider="anthropic", credentials_enc="1", model="claude-sonnet-5", user_id=user_id)
    outra = _FakeConfig(provider="deepseek", credentials_enc="2", model="deepseek-chat", user_id=user_id, enabled=True)
    override = _FakeOverride(provider_config_id=outra.id)
    session = _FakeSession(
        _RowsResult([padrao]), _ScalarResult(override),
        get_map={(AIProviderConfig, outra.id): outra},
    )

    async with byok_mod.user_ai_creds(session, user_id, task_type="analytics_report"):
        creds = ai_creds_ctx.get()
        assert creds["provider"] == "deepseek"
        assert creds["model"] == "deepseek-chat"
        assert creds["api_key"] == "sk-2"


@pytest.mark.asyncio
async def test_override_com_config_removida_cai_no_model_legado(monkeypatch):
    import app.core.crypto as crypto_mod
    monkeypatch.setattr(crypto_mod, "decrypt", lambda tok: '{"api_key": "sk-1"}')

    user_id = uuid.uuid4()
    padrao = _FakeConfig(provider="anthropic", credentials_enc="1", model="claude-sonnet-5", user_id=user_id)
    config_id_removida = uuid.uuid4()
    override = _FakeOverride(model="claude-opus-4-8", provider_config_id=config_id_removida)
    session = _FakeSession(
        _RowsResult([padrao]), _ScalarResult(override),
        get_map={},  # config_id_removida não existe mais
    )

    async with byok_mod.user_ai_creds(session, user_id, task_type="generate_petition"):
        creds = ai_creds_ctx.get()
        assert creds["provider"] == "anthropic"  # continua a padrão
        assert creds["model"] == "claude-opus-4-8"  # cai pro model legado


@pytest.mark.asyncio
async def test_override_com_config_de_outro_usuario_e_ignorado(monkeypatch):
    """Defesa em profundidade: mesmo que um provider_config_id de outro
    usuário chegasse até aqui, nunca deveria ser aplicado."""
    from app.models.ai_config import AIProviderConfig
    import app.core.crypto as crypto_mod
    monkeypatch.setattr(crypto_mod, "decrypt", lambda tok: '{"api_key": "sk-1"}')

    user_id = uuid.uuid4()
    outro_user_id = uuid.uuid4()
    padrao = _FakeConfig(provider="anthropic", credentials_enc="1", model="claude-sonnet-5", user_id=user_id)
    config_de_outro = _FakeConfig(provider="deepseek", credentials_enc="2", model="deepseek-chat", user_id=outro_user_id)
    override = _FakeOverride(provider_config_id=config_de_outro.id)
    session = _FakeSession(
        _RowsResult([padrao]), _ScalarResult(override),
        get_map={(AIProviderConfig, config_de_outro.id): config_de_outro},
    )

    async with byok_mod.user_ai_creds(session, user_id, task_type="generate_petition"):
        creds = ai_creds_ctx.get()
        assert creds["provider"] == "anthropic"  # config de outro usuário nunca aplicada
        assert creds["model"] == "claude-sonnet-5"
