"""Fase 112 — cache de busca RAG por hash de query+tenant (Redis, TTL curto).
Confirma cache-hit evita reembedar/rebuscar, isolamento entre tenants, e
degradação graciosa sem Redis (comportamento idêntico ao anterior)."""
import uuid
import pytest

import app.rag.retrieval as retrieval_mod

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value


class _FakeQdrantClient:
    """Fase 187 — achado da Fase 186: a versão anterior deste Fake tinha um
    método `search()` manual que nunca validou contra a API real da lib
    instalada, mascarando que `AsyncQdrantClient.search()` não existe mais
    (renomeado pra `.query_points()`, que devolve um objeto com `.points`,
    não uma lista direta) — busca RAG real ficou quebrada silenciosamente
    até a Fase 187 corrigir `retrieval.py`. Este Fake agora espelha a forma
    real de `query_points()`."""
    def __init__(self):
        self.search_calls = 0

    async def query_points(self, **kwargs):
        self.search_calls += 1
        hit = type("Hit", (), {
            "score": 0.9, "id": "abc",
            "payload": {"text": "resultado real"},
        })()
        return type("QueryResponse", (), {"points": [hit]})()


@pytest.mark.asyncio
async def test_segunda_chamada_identica_usa_cache_sem_reembedar(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(retrieval_mod, "get_redis", lambda: _async_return(fake_redis))

    embed_calls = {"n": 0}

    async def fake_embed_text_with_meta(query, force_system_default=False):
        embed_calls["n"] += 1
        return [0.1, 0.2, 0.3], "openai", "text-embedding-3-large"

    monkeypatch.setattr(retrieval_mod, "embed_text_with_meta", fake_embed_text_with_meta)

    client = _FakeQdrantClient()
    r1 = await retrieval_mod.retrieve(client, "citação de lei X", collections=["legislacao"], tenant_id=TENANT_A)
    r2 = await retrieval_mod.retrieve(client, "citação de lei X", collections=["legislacao"], tenant_id=TENANT_A)

    assert r1 == r2
    assert embed_calls["n"] == 1  # só a 1ª chamada embedou de verdade
    assert client.search_calls == 1  # só a 1ª chamada bateu no Qdrant


@pytest.mark.asyncio
async def test_tenants_diferentes_nao_compartilham_cache(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(retrieval_mod, "get_redis", lambda: _async_return(fake_redis))
    monkeypatch.setattr(retrieval_mod, "embed_text_with_meta", lambda query, force_system_default=False: _async_return_meta())

    client = _FakeQdrantClient()
    await retrieval_mod.retrieve(client, "mesma query", collections=["peticoes_afj"], tenant_id=TENANT_A)
    await retrieval_mod.retrieve(client, "mesma query", collections=["peticoes_afj"], tenant_id=TENANT_B)

    assert client.search_calls == 2  # cada tenant bateu no Qdrant — chave inclui tenant_id


@pytest.mark.asyncio
async def test_sem_redis_comportamento_identico_ao_anterior(monkeypatch):
    monkeypatch.setattr(retrieval_mod, "get_redis", lambda: _async_return(None))
    monkeypatch.setattr(retrieval_mod, "embed_text_with_meta", lambda query, force_system_default=False: _async_return_meta())

    client = _FakeQdrantClient()
    r1 = await retrieval_mod.retrieve(client, "consulta sem cache", collections=["legislacao"])
    r2 = await retrieval_mod.retrieve(client, "consulta sem cache", collections=["legislacao"])

    assert r1 == r2
    assert client.search_calls == 2  # sem Redis, sempre busca de verdade


async def _async_return(value):
    return value


async def _async_return_meta():
    return [0.1, 0.2, 0.3], "openai", "text-embedding-3-large"


@pytest.mark.asyncio
async def test_provedores_byok_diferentes_no_mesmo_tenant_nao_compartilham_cache(monkeypatch):
    """Dois usuários do MESMO escritório, com BYOK de provedores diferentes,
    fazendo a MESMA pergunta na MESMA collection privada.

    Antes desta correção os dois colidiam na mesma entrada de cache por 300s:
    `_cache_key()` tinha query/collections/filters/k/threshold/tenant_id, mas
    não o provedor — e a chave era montada ANTES de `embed_text_with_meta()`
    resolver qual provedor o BYOK ativava. O segundo usuário recebia o
    resultado já filtrado por `_provider_filter()` para o provedor do
    primeiro, contradizendo a invariante criada no desacoplamento de
    provedores. Não é vazamento entre escritórios (tenant_id sempre esteve na
    chave) — é resultado errado dentro do mesmo escritório.

    O teste exercita a resolução REAL (seta o contextvar de BYOK que
    `user_ai_creds()` usa em produção), não um monkeypatch do resolvedor:
    assim ele também quebra se a chave e o embedding passarem a resolver o
    provedor por caminhos diferentes."""
    from app.integrations.llm_client import ai_creds_ctx

    fake_redis = _FakeRedis()
    monkeypatch.setattr(retrieval_mod, "get_redis", lambda: _async_return(fake_redis))

    async def embed_conforme_byok(query, force_system_default=False):
        creds = ai_creds_ctx.get() or {}
        provider = "openai" if force_system_default else (creds.get("provider") or "openai")
        return [0.1, 0.2, 0.3], provider, "modelo-x"

    monkeypatch.setattr(retrieval_mod, "embed_text_with_meta", embed_conforme_byok)

    client = _FakeQdrantClient()

    token = ai_creds_ctx.set({"provider": "openai", "api_key": "sk-teste-openai", "base_url": None})
    try:
        await retrieval_mod.retrieve(client, "mesma pergunta", collections=["peticoes_afj"], tenant_id=TENANT_A)
    finally:
        ai_creds_ctx.reset(token)

    token = ai_creds_ctx.set({"provider": "gemini", "api_key": "key-teste-gemini", "base_url": "https://g/"})
    try:
        await retrieval_mod.retrieve(client, "mesma pergunta", collections=["peticoes_afj"], tenant_id=TENANT_A)
    finally:
        ai_creds_ctx.reset(token)

    # Duas buscas reais no Qdrant: o provedor faz parte da chave.
    assert client.search_calls == 2
    assert len(fake_redis.store) == 2

    # E o cache continua funcionando para o MESMO provedor (não viramos
    # "cache que nunca acerta", que seria uma regressão de custo).
    token = ai_creds_ctx.set({"provider": "gemini", "api_key": "key-teste-gemini", "base_url": "https://g/"})
    try:
        await retrieval_mod.retrieve(client, "mesma pergunta", collections=["peticoes_afj"], tenant_id=TENANT_A)
    finally:
        ai_creds_ctx.reset(token)
    assert client.search_calls == 2  # cache-hit, não bateu no Qdrant de novo


@pytest.mark.asyncio
async def test_collection_publica_nao_muda_de_chave_com_byok_do_usuario(monkeypatch):
    """Busca em collection PÚBLICA sempre resolve para o provedor padrão da
    plataforma, então o BYOK do usuário não pode fragmentar esse cache — os
    dois usuários devem compartilhar a mesma entrada (o conteúdo público é
    idêntico para os dois)."""
    from app.integrations.llm_client import ai_creds_ctx

    fake_redis = _FakeRedis()
    monkeypatch.setattr(retrieval_mod, "get_redis", lambda: _async_return(fake_redis))
    monkeypatch.setattr(retrieval_mod, "embed_text_with_meta",
                        lambda query, force_system_default=False: _async_return_meta())

    client = _FakeQdrantClient()

    for provider in ("openai", "gemini"):
        token = ai_creds_ctx.set({"provider": provider, "api_key": f"key-{provider}", "base_url": None})
        try:
            await retrieval_mod.retrieve(client, "lei pública", collections=["legislacao"], tenant_id=TENANT_A)
        finally:
            ai_creds_ctx.reset(token)

    assert client.search_calls == 1  # mesma entrada de cache para os dois
