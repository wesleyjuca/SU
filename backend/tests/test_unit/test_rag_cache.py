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
    def __init__(self):
        self.search_calls = 0

    async def search(self, **kwargs):
        self.search_calls += 1
        hit = type("Hit", (), {
            "score": 0.9, "id": "abc",
            "payload": {"text": "resultado real"},
        })()
        return [hit]


@pytest.mark.asyncio
async def test_segunda_chamada_identica_usa_cache_sem_reembedar(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(retrieval_mod, "get_redis", lambda: _async_return(fake_redis))

    embed_calls = {"n": 0}

    async def fake_embed_text(query):
        embed_calls["n"] += 1
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr(retrieval_mod, "embed_text", fake_embed_text)

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
    monkeypatch.setattr(retrieval_mod, "embed_text", lambda query: _async_return([0.1, 0.2, 0.3]))

    client = _FakeQdrantClient()
    await retrieval_mod.retrieve(client, "mesma query", collections=["peticoes_afj"], tenant_id=TENANT_A)
    await retrieval_mod.retrieve(client, "mesma query", collections=["peticoes_afj"], tenant_id=TENANT_B)

    assert client.search_calls == 2  # cada tenant bateu no Qdrant — chave inclui tenant_id


@pytest.mark.asyncio
async def test_sem_redis_comportamento_identico_ao_anterior(monkeypatch):
    monkeypatch.setattr(retrieval_mod, "get_redis", lambda: _async_return(None))
    monkeypatch.setattr(retrieval_mod, "embed_text", lambda query: _async_return([0.1, 0.2, 0.3]))

    client = _FakeQdrantClient()
    r1 = await retrieval_mod.retrieve(client, "consulta sem cache", collections=["legislacao"])
    r2 = await retrieval_mod.retrieve(client, "consulta sem cache", collections=["legislacao"])

    assert r1 == r2
    assert client.search_calls == 2  # sem Redis, sempre busca de verdade


async def _async_return(value):
    return value
