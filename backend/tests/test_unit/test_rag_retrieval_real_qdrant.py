"""Fase 187 — teste de regressão contra Qdrant REAL em memória (não um Fake
escrito à mão) pro achado da Fase 186: `AsyncQdrantClient.search()` não
existe mais na versão pinada em requirements.txt (1.18.0, renomeado pra
`.query_points()`) — todo teste anterior de `retrieve()` usava um Fake com
um método `search()` definido manualmente, que nunca validou contra a API
real da lib instalada, e por isso nunca pegou o bug. `location=":memory:"`
do qdrant-client sobe um motor real (não um mock) sem precisar de um
servidor Qdrant de verdade — usar isso aqui, e não outro Fake, é o que
efetivamente fecha essa lacuna de cobertura."""
import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.config import settings
from app.rag.retrieval import retrieve

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def qdrant_memoria():
    client = AsyncQdrantClient(location=":memory:")
    await client.create_collection(
        collection_name="legislacao",
        vectors_config=VectorParams(size=settings.EMBEDDING_DIMENSIONS, distance=Distance.COSINE),
    )
    await client.upsert(
        collection_name="legislacao",
        points=[PointStruct(id=1, vector=[0.01] * settings.EMBEDDING_DIMENSIONS, payload={"text": "art. 5º da lei de teste"})],
    )
    return client


async def test_retrieve_encontra_resultado_real_via_query_points(qdrant_memoria, monkeypatch):
    """Se `retrieve()` ainda chamasse `.search()` (removido da lib
    instalada), isso levantaria AttributeError — engolido pelo `except
    Exception` por coleção — e este teste falharia com resultados=[]."""
    import app.rag.retrieval as retrieval_mod

    async def _fake_embed_text_with_meta(query, force_system_default=False):
        return [0.0105] * settings.EMBEDDING_DIMENSIONS, "openai", "text-embedding-3-large"

    async def _no_redis():
        return None

    monkeypatch.setattr(retrieval_mod, "embed_text_with_meta", _fake_embed_text_with_meta)
    monkeypatch.setattr(retrieval_mod, "get_redis", _no_redis)

    resultados = await retrieve(qdrant_memoria, "art. 5º", collections=["legislacao"], score_threshold=0.0)

    assert len(resultados) == 1
    assert resultados[0]["text"] == "art. 5º da lei de teste"
    assert resultados[0]["collection"] == "legislacao"
