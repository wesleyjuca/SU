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
from app.rag.embeddings import (
    _resolve_byok_openai_key,
    _resolve_embedding_credentials,
    embed_batch_with_meta,
    get_embeddings_client,
)


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
        from types import SimpleNamespace

        n = len(input) if isinstance(input, list) else 1
        itens = [SimpleNamespace(index=i, embedding=[0.0]) for i in range(n)]
        return SimpleNamespace(data=itens)


@pytest.fixture(autouse=True)
def _fake_asyncopenai(monkeypatch):
    """Evita construir um AsyncOpenAI real (sem chamada de rede) — só
    interessa aqui qual provider/model/dimensions o dispatch resolve."""
    import app.rag.embeddings as embeddings_mod

    class _FakeAsyncOpenAI:
        def __init__(self, api_key=None, base_url=None, timeout=None):
            self.api_key = api_key
            self.base_url = base_url
            self.timeout = timeout
            self.embeddings = _FakeEmbeddingsAPI()
            self.closed = False

        async def close(self):
            self.closed = True

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


# Achado real de produção (fase pós-264, sync da Doutrina): sem timeout
# explícito, um lote de embedding lento/rate-limitado podia consumir tempo
# suficiente pra colidir com o soft_time_limit da task Celery, e a
# interrupção no meio de uma chamada de rede corrompia o event loop
# ("Event loop is closed" em chamadas seguintes no mesmo processo).


@pytest.mark.asyncio
async def test_get_embeddings_client_byok_passa_timeout_explicito():
    from app.rag.embeddings import _EMBEDDING_TIMEOUT_SECONDS

    ai_creds_ctx.set({"provider": "gemini", "api_key": "gm-key", "base_url": None})
    client, _provider, _model, _dimensions = get_embeddings_client()
    assert client.timeout == _EMBEDDING_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_get_embeddings_client_singleton_passa_timeout_explicito(monkeypatch):
    from app.config import settings
    from app.rag.embeddings import _EMBEDDING_TIMEOUT_SECONDS

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-central")
    client, _provider, _model, _dimensions = get_embeddings_client()
    assert client.timeout == _EMBEDDING_TIMEOUT_SECONDS


# Achado real de produção (fase pós-264, sync da Doutrina): o client BYOK
# (criado do zero a cada chamada) nunca era fechado — vazamento de recurso
# real, diferente de todo outro client HTTP do projeto. O singleton do
# provedor padrão precisa continuar VIVO entre chamadas do mesmo processo
# (fechado só por `run_worker_coro`, no fim de cada task Celery).


@pytest.mark.asyncio
async def test_embed_text_fecha_client_byok_apos_uso():
    import app.rag.embeddings as embeddings_mod

    ai_creds_ctx.set({"provider": "gemini", "api_key": "gm-key", "base_url": None})
    await embeddings_mod.embed_text_with_meta("um texto qualquer")
    # O client usado nessa chamada nunca fica acessível fora da função —
    # a prova indireta é que o singleton continua None (BYOK nunca o toca).
    assert embeddings_mod._client is None


@pytest.mark.asyncio
async def test_embed_text_nao_fecha_singleton_do_provedor_padrao(monkeypatch):
    import app.rag.embeddings as embeddings_mod
    from app.config import settings

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-central")
    await embeddings_mod.embed_text_with_meta("um texto qualquer")
    # Prova real: o singleton sobrevive à chamada e não foi fechado —
    # se o fix fechasse o singleton por engano, esta asserção falharia.
    assert embeddings_mod._client is not None
    assert embeddings_mod._client.closed is False


@pytest.mark.asyncio
async def test_embed_batch_fecha_client_byok_apos_uso(monkeypatch):
    """Mesma prova acima, via um fake que expõe o client construído pra
    conseguir inspecionar `.closed` diretamente (o teste anterior só prova
    indiretamente via o singleton continuar None)."""
    import app.rag.embeddings as embeddings_mod

    clients_criados = []

    class _FakeAsyncOpenAIRastreado:
        def __init__(self, api_key=None, base_url=None, timeout=None):
            self.api_key = api_key
            self.embeddings = _FakeEmbeddingsAPI()
            self.closed = False
            clients_criados.append(self)

        async def close(self):
            self.closed = True

    monkeypatch.setattr(embeddings_mod, "AsyncOpenAI", _FakeAsyncOpenAIRastreado)
    ai_creds_ctx.set({"provider": "gemini", "api_key": "gm-key", "base_url": None})

    await embeddings_mod.embed_batch_with_meta(["texto 1", "texto 2"])

    assert len(clients_criados) == 1
    assert clients_criados[0].closed is True


# Achado real de produção (auditoria pós-262.2): `BatchEmbedContentsRequest.
# requests: at most 100 requests can be in one batch` (HTTP 400) — a API do
# Gemini rejeita qualquer chamada com mais de 100 itens; `embed_batch_with_meta`
# nunca fatiava a lista, funcionava só por acidente com OpenAI (sem teto
# conhecido). Testado com um fake client que grava o tamanho de cada chamada.


class _FakeItem:
    def __init__(self, index, value):
        self.index = index
        self.embedding = value


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeEmbeddingsAPIRecorder:
    def __init__(self):
        self.chamadas: list[list[str]] = []

    async def create(self, input, model, dimensions):
        self.chamadas.append(list(input))
        # Devolve na ordem embaralhada de propósito, pra provar que o
        # reordenamento por `.index` dentro de CADA lote continua correto.
        itens = [_FakeItem(i, [float(i)]) for i in range(len(input))]
        return _FakeResponse(list(reversed(itens)))


@pytest.fixture
def _fake_recorder(monkeypatch):
    import app.rag.embeddings as embeddings_mod

    recorder = _FakeEmbeddingsAPIRecorder()

    class _FakeAsyncOpenAI:
        def __init__(self, api_key=None, base_url=None, timeout=None):
            self.embeddings = recorder

        async def close(self):
            pass

    monkeypatch.setattr(embeddings_mod, "AsyncOpenAI", _FakeAsyncOpenAI)
    embeddings_mod._client = None
    yield recorder
    embeddings_mod._client = None


@pytest.mark.asyncio
async def test_embed_batch_gemini_fatia_em_lotes_de_100(_fake_recorder):
    ai_creds_ctx.set({"provider": "gemini", "api_key": "gm-key", "base_url": None})
    textos = [f"texto {i}" for i in range(250)]

    vetores, provider, model = await embed_batch_with_meta(textos)

    assert provider == "gemini"
    assert len(_fake_recorder.chamadas) == 3
    assert [len(c) for c in _fake_recorder.chamadas] == [100, 100, 50]
    assert len(vetores) == 250
    # Ordem preservada apesar do embaralhamento dentro de cada lote.
    assert vetores == [[float(i)] for i in range(100)] + [[float(i)] for i in range(100)] + [[float(i)] for i in range(50)]


@pytest.mark.asyncio
async def test_embed_batch_openai_nao_fatia_mesmo_com_muitos_itens(_fake_recorder):
    """Prova nos dois sentidos: reverter o fix (remover `embedding_max_batch`
    do registro do Gemini, ou remover o fatiamento) faria o teste acima
    falhar; este aqui confirma que a OpenAI (sem teto conhecido) continua
    recebendo 1 chamada só, sem regressão de comportamento."""
    ai_creds_ctx.set({"provider": "openai", "api_key": "sk-key", "base_url": None})
    textos = [f"texto {i}" for i in range(250)]

    vetores, provider, model = await embed_batch_with_meta(textos)

    assert provider == "openai"
    assert len(_fake_recorder.chamadas) == 1
    assert len(_fake_recorder.chamadas[0]) == 250
    assert len(vetores) == 250


@pytest.mark.asyncio
async def test_embed_batch_gemini_com_poucos_itens_nao_fatia(_fake_recorder):
    ai_creds_ctx.set({"provider": "gemini", "api_key": "gm-key", "base_url": None})
    textos = [f"texto {i}" for i in range(30)]

    vetores, provider, model = await embed_batch_with_meta(textos)

    assert len(_fake_recorder.chamadas) == 1
    assert len(vetores) == 30


# Achado real de produção (fase pós-264): o SDK da OpenAI desserializa a
# resposta sem validação (`BaseModel.construct()`) — se a camada de
# compatibilidade OpenAI do Gemini omitir "index" em algum item do lote, o
# campo vira `None` em silêncio, e `sorted(..., key=lambda x: x.index)`
# explode com "'<' not supported between instances of 'int' and 'NoneType'"
# (Timsort usa `__lt__` internamente pra qualquer comparação de ordem).
# Falha alta e explícita é mais segura que presumir a ordem de entrada.


class _FakeEmbeddingsAPIIndiceAusente:
    """Devolve 1 item com `index=None` entre os demais — reproduz o defeito
    real observado na camada de compatibilidade do Gemini."""

    async def create(self, input, model, dimensions):
        itens = [_FakeItem(i, [float(i)]) for i in range(len(input))]
        itens[1].index = None
        return _FakeResponse(itens)


@pytest.fixture
def _fake_indice_ausente(monkeypatch):
    import app.rag.embeddings as embeddings_mod

    class _FakeAsyncOpenAI:
        def __init__(self, api_key=None, base_url=None, timeout=None):
            self.embeddings = _FakeEmbeddingsAPIIndiceAusente()

        async def close(self):
            pass

    monkeypatch.setattr(embeddings_mod, "AsyncOpenAI", _FakeAsyncOpenAI)
    embeddings_mod._client = None
    yield
    embeddings_mod._client = None


@pytest.mark.asyncio
async def test_embed_batch_com_index_ausente_falha_alto_com_mensagem_clara(_fake_indice_ausente):
    ai_creds_ctx.set({"provider": "gemini", "api_key": "gm-key", "base_url": None})

    with pytest.raises(RuntimeError, match="sem 'index'"):
        await embed_batch_with_meta(["texto 0", "texto 1", "texto 2"])


@pytest.mark.asyncio
async def test_embed_batch_sem_index_ausente_continua_ordenando_normalmente(_fake_recorder):
    """Prova nos dois sentidos: sem o guard, este teste continuaria
    passando (nenhum índice é None aqui) — é o teste acima que prova que o
    guard dispara exatamente quando deveria, e só então."""
    ai_creds_ctx.set({"provider": "gemini", "api_key": "gm-key", "base_url": None})

    vetores, _provider, _model = await embed_batch_with_meta(["a", "b", "c"])

    assert vetores == [[0.0], [1.0], [2.0]]
