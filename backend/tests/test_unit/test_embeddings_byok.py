"""Achado real (validação pós-merge da Fase 258/259): `_resolve_byok_openai_key`
(`app/rag/embeddings.py`) só considerava a config de IA PADRÃO/primária do
usuário (`ai_creds_ctx`) — um usuário com Anthropic como padrão (o comum,
já que é o provedor usado no resto do sistema) e uma chave OpenAI cadastrada
só como config SECUNDÁRIA (`ai_fallback_ctx`, a cadeia de fallback que
`user_ai_creds()` já expõe) nunca tinha essa chave considerada aqui, mesmo
com uma OpenAI válida cadastrada — a Pesquisa Jurídica (RAG) continuava
exigindo `OPENAI_API_KEY` central mesmo quando o usuário já tinha resolvido
o problema do jeito certo (cadastrando uma chave OpenAI em "Minha IA")."""
import pytest

from app.integrations.llm_client import ai_creds_ctx, ai_fallback_ctx
from app.rag.embeddings import _resolve_byok_openai_key, _resolve_embedding_credentials, get_embeddings_client


@pytest.fixture(autouse=True)
def _limpa_contextvars():
    tok1 = ai_creds_ctx.set(None)
    tok2 = ai_fallback_ctx.set(None)
    yield
    ai_creds_ctx.reset(tok1)
    ai_fallback_ctx.reset(tok2)


def test_sem_nenhuma_config_devolve_none():
    assert _resolve_byok_openai_key() == (None, None)


def test_primaria_openai_e_usada_diretamente():
    ai_creds_ctx.set({"provider": "openai", "api_key": "sk-primaria", "base_url": None})
    assert _resolve_byok_openai_key() == ("sk-primaria", None)


def test_primaria_anthropic_sem_fallback_devolve_none():
    ai_creds_ctx.set({"provider": "anthropic", "api_key": "sk-ant-primaria", "base_url": None})
    assert _resolve_byok_openai_key() == (None, None)


def test_primaria_anthropic_com_openai_no_fallback_e_encontrada():
    """O cenário real do achado: Anthropic como padrão, OpenAI só como
    config secundária habilitada — antes do fix isso sempre falhava."""
    ai_creds_ctx.set({"provider": "anthropic", "api_key": "sk-ant-primaria", "base_url": None})
    ai_fallback_ctx.set([
        {"provider": "gemini", "api_key": "gm-secundaria", "base_url": None},
        {"provider": "openai", "api_key": "sk-fallback", "base_url": None},
    ])
    assert _resolve_byok_openai_key() == ("sk-fallback", None)


def test_primaria_vence_mesmo_com_openai_no_fallback():
    """Se a PRÓPRIA primária já é openai, o fallback nem precisa ser
    percorrido — preserva a prioridade original do usuário."""
    ai_creds_ctx.set({"provider": "openai", "api_key": "sk-primaria-openai", "base_url": None})
    ai_fallback_ctx.set([{"provider": "openai", "api_key": "sk-fallback-openai", "base_url": None}])
    assert _resolve_byok_openai_key() == ("sk-primaria-openai", None)


def test_openai_sem_api_key_no_fallback_e_ignorada():
    ai_creds_ctx.set({"provider": "anthropic", "api_key": "sk-ant", "base_url": None})
    ai_fallback_ctx.set([{"provider": "openai", "api_key": "", "base_url": None}])
    assert _resolve_byok_openai_key() == (None, None)


def test_base_url_customizado_e_preservado():
    ai_creds_ctx.set({"provider": "anthropic", "api_key": "sk-ant", "base_url": None})
    ai_fallback_ctx.set([{"provider": "openai", "api_key": "sk-fallback", "base_url": "https://proxy.exemplo.com/v1"}])
    assert _resolve_byok_openai_key() == ("sk-fallback", "https://proxy.exemplo.com/v1")


def test_nenhum_provider_openai_em_lugar_nenhum_devolve_none():
    ai_creds_ctx.set({"provider": "anthropic", "api_key": "sk-ant", "base_url": None})
    ai_fallback_ctx.set([{"provider": "gemini", "api_key": "gm", "base_url": None}])
    assert _resolve_byok_openai_key() == (None, None)


# Fase pós-260 — `_resolve_embedding_credentials()` generaliza o resolver
# acima pra qualquer provedor embedding-capable (hoje openai/gemini), não
# mais hardcoded só pra "openai".


def test_resolve_generico_sem_nenhuma_config_devolve_none():
    assert _resolve_embedding_credentials() == (None, None, None)


def test_resolve_generico_primaria_openai():
    ai_creds_ctx.set({"provider": "openai", "api_key": "sk-primaria", "base_url": None})
    assert _resolve_embedding_credentials() == ("openai", "sk-primaria", None)


def test_resolve_generico_primaria_gemini():
    ai_creds_ctx.set({"provider": "gemini", "api_key": "gm-primaria", "base_url": None})
    assert _resolve_embedding_credentials() == ("gemini", "gm-primaria", None)


def test_resolve_generico_primaria_anthropic_sem_fallback_devolve_none():
    """Anthropic não tem API de embeddings — corretamente excluído do
    registro central (`embedding_capable_providers()`), mesmo sendo a
    config primária/padrão do usuário."""
    ai_creds_ctx.set({"provider": "anthropic", "api_key": "sk-ant", "base_url": None})
    assert _resolve_embedding_credentials() == (None, None, None)


def test_resolve_generico_primaria_anthropic_com_gemini_no_fallback():
    """Cenário real: Anthropic como IA padrão (comum), Gemini cadastrado só
    como fallback secundário — varre a cadeia inteira, não só a primária."""
    ai_creds_ctx.set({"provider": "anthropic", "api_key": "sk-ant", "base_url": None})
    ai_fallback_ctx.set([{"provider": "gemini", "api_key": "gm-fallback", "base_url": None}])
    assert _resolve_embedding_credentials() == ("gemini", "gm-fallback", None)


def test_resolve_generico_respeita_ordem_de_prioridade_entre_openai_e_gemini():
    """Os dois provedores no fallback, em ordens diferentes — o resolver
    genérico sempre acha o PRIMEIRO embedding-capable da cadeia, respeitando
    a prioridade configurada pelo usuário (não uma preferência fixa por
    provedor)."""
    ai_creds_ctx.set({"provider": "anthropic", "api_key": "sk-ant", "base_url": None})
    ai_fallback_ctx.set([
        {"provider": "gemini", "api_key": "gm-1o", "base_url": None},
        {"provider": "openai", "api_key": "sk-2o", "base_url": None},
    ])
    assert _resolve_embedding_credentials() == ("gemini", "gm-1o", None)

    ai_fallback_ctx.set([
        {"provider": "openai", "api_key": "sk-1o", "base_url": None},
        {"provider": "gemini", "api_key": "gm-2o", "base_url": None},
    ])
    assert _resolve_embedding_credentials() == ("openai", "sk-1o", None)


def test_resolve_generico_ignora_grok_sem_suporte_a_embeddings():
    ai_creds_ctx.set({"provider": "grok", "api_key": "xai-key", "base_url": None})
    ai_fallback_ctx.set([{"provider": "openai", "api_key": "sk-fallback", "base_url": None}])
    assert _resolve_embedding_credentials() == ("openai", "sk-fallback", None)


class _FakeEmbeddingsAPI:
    async def create(self, input, model, dimensions):
        return None


@pytest.fixture(autouse=True)
def _fake_asyncopenai(monkeypatch):
    """Evita construir um AsyncOpenAI real (sem chamada de rede) — só
    interessa aqui qual provider/model/dimensions o dispatch resolve."""
    import app.rag.embeddings as embeddings_mod

    class _FakeAsyncOpenAI:
        def __init__(self, api_key=None, base_url=None):
            self.api_key = api_key
            self.base_url = base_url
            self.embeddings = _FakeEmbeddingsAPI()

    monkeypatch.setattr(embeddings_mod, "AsyncOpenAI", _FakeAsyncOpenAI)
    embeddings_mod._client = None
    yield
    embeddings_mod._client = None


@pytest.mark.asyncio
async def test_get_embeddings_client_dispatch_openai_byok():
    ai_creds_ctx.set({"provider": "openai", "api_key": "sk-openai", "base_url": None})
    client, provider, model, dimensions = get_embeddings_client()
    assert provider == "openai"
    assert model == "text-embedding-3-large"
    assert dimensions == 3072
    assert client.api_key == "sk-openai"


@pytest.mark.asyncio
async def test_get_embeddings_client_dispatch_gemini_byok():
    ai_creds_ctx.set({"provider": "gemini", "api_key": "gm-key", "base_url": None})
    client, provider, model, dimensions = get_embeddings_client()
    assert provider == "gemini"
    assert model == "gemini-embedding-001"
    assert dimensions == 3072
    assert client.api_key == "gm-key"


@pytest.mark.asyncio
async def test_get_embeddings_client_force_system_default_ignora_byok(monkeypatch):
    """`force_system_default=True` sempre ignora o contexto BYOK, mesmo
    com uma credencial embedding-capable ativa — usado pelas collections
    públicas/compartilhadas."""
    from app.config import settings

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-central")
    ai_creds_ctx.set({"provider": "gemini", "api_key": "gm-key", "base_url": None})

    client, provider, model, dimensions = get_embeddings_client(force_system_default=True)
    assert provider == "openai"
    assert client.api_key == "sk-central"


@pytest.mark.asyncio
async def test_get_embeddings_client_dispatch_anthropic_cai_no_padrao_do_sistema(monkeypatch):
    """Anthropic não é embedding-capable — mesmo sendo a config ativa,
    `get_embeddings_client()` cai pro padrão do sistema (nunca `None`)."""
    from app.config import settings

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-central")
    ai_creds_ctx.set({"provider": "anthropic", "api_key": "sk-ant", "base_url": None})

    client, provider, model, dimensions = get_embeddings_client()
    assert provider == "openai"
    assert client.api_key == "sk-central"
