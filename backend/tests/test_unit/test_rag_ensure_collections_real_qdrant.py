"""Fase 198 — teste de regressão contra Qdrant REAL em memória pro achado
da Fase 197: `ensure_collections()` (app/rag/collections.py) iterava
`get_collections()` como se o retorno já fosse a lista de collections —
na verdade é um `CollectionsResponse` (pydantic), cujo campo é
`.collections`. Iterar o objeto direto dá `[("collections", [...])]`
(campos do pydantic model), e `c.name` explode com AttributeError. Mesma
classe de risco da Fase 186/187 (Fake de teste nunca bateu a API real da
lib pinada) — aqui não havia teste nenhum, Fake ou real."""
import pytest
from qdrant_client import AsyncQdrantClient

from app.rag.collections import ensure_collections, COLLECTIONS

pytestmark = pytest.mark.asyncio


async def test_ensure_collections_cria_todas_as_collections_com_qdrant_real():
    client = AsyncQdrantClient(location=":memory:")
    await ensure_collections(client)
    existentes = {c.name for c in (await client.get_collections()).collections}
    assert existentes == set(COLLECTIONS.keys())


async def test_ensure_collections_e_idempotente():
    client = AsyncQdrantClient(location=":memory:")
    await ensure_collections(client)
    await ensure_collections(client)  # não pode levantar nem duplicar
    existentes = {c.name for c in (await client.get_collections()).collections}
    assert existentes == set(COLLECTIONS.keys())


async def test_ensure_collections_nao_recria_collection_ja_existente_com_dados():
    client = AsyncQdrantClient(location=":memory:")
    await ensure_collections(client)
    from qdrant_client.models import PointStruct
    config = COLLECTIONS["legislacao"]
    await client.upsert(
        collection_name="legislacao",
        points=[PointStruct(id=1, vector=[0.1] * config["vector_size"], payload={"text": "ponto de teste"})],
    )
    await ensure_collections(client)  # não pode apagar/recriar a collection existente
    count = (await client.count(collection_name="legislacao")).count
    assert count == 1
