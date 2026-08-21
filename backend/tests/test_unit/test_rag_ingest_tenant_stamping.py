"""Fase 204 (achado ALTO da Fase 203) — POST /rag/ingest aceitava `tenant_id`
livre dentro de `metadata` no payload do cliente, sem nunca sobrescrever com
o `tenant_id` real do chamador. Como `retrieve()` confia cegamente nesse
campo pra isolar as collections privadas (PRIVATE_COLLECTIONS), um ADMIN do
tenant A podia forjar `tenant_id` do tenant B e ter o conteúdo malicioso
servido de volta como se fosse dado confiável do escritório B.

Qdrant real em memória (não um Fake escrito à mão), mesmo padrão das Fases
187/198.A/202 — o fix mexe em código que já teve um bug de API real vs Fake
divergente, então usar o motor de verdade aqui é o que garante que o teste
não sobreviva a uma regressão por engano."""
import uuid

import pytest
from qdrant_client import AsyncQdrantClient

from app.config import settings
from app.rag.collections import ensure_collections
from app.rag.retrieval import retrieve

pytestmark = pytest.mark.asyncio


class _FakeUser:
    def __init__(self, user_id, tenant_id):
        self.id = user_id
        self.tenant_id = tenant_id


@pytest.fixture
async def qdrant_memoria():
    client = AsyncQdrantClient(location=":memory:")
    await ensure_collections(client)
    return client


async def test_ingest_ignora_tenant_id_forjado_no_payload_privado(qdrant_memoria, monkeypatch):
    import app.api.v1.rag as rag_mod
    import app.rag.ingestion as ingestion_mod
    import app.rag.retrieval as retrieval_mod

    async def _fake_get_qdrant():
        return qdrant_memoria

    async def _fake_embed_batch(texts):
        return [[0.02] * settings.EMBEDDING_DIMENSIONS for _ in texts]

    async def _fake_embed_text(text):
        return [0.02] * settings.EMBEDDING_DIMENSIONS

    async def _no_redis():
        return None

    monkeypatch.setattr(ingestion_mod, "get_qdrant", _fake_get_qdrant)
    monkeypatch.setattr(ingestion_mod, "embed_batch", _fake_embed_batch)
    monkeypatch.setattr(retrieval_mod, "embed_text", _fake_embed_text)
    monkeypatch.setattr(retrieval_mod, "get_redis", _no_redis)

    tenant_atacante = str(uuid.uuid4())
    tenant_vitima = str(uuid.uuid4())
    admin_atacante = _FakeUser(uuid.uuid4(), tenant_atacante)

    req = rag_mod.IngestRequest(
        content="conteudo malicioso plantado pelo atacante",
        collection="documentos_clientes",
        # tentativa de forjar o tenant_id de OUTRO escritório
        metadata={"tenant_id": tenant_vitima, "titulo": "Peça forjada"},
    )

    resultado = await rag_mod.rag_ingest(req, db=None, current_user=admin_atacante)
    assert resultado["chunks_created"] == 1

    # A vítima NÃO deve ver o conteúdo plantado na busca do próprio tenant.
    achados_vitima = await retrieve(
        qdrant_memoria, "conteudo malicioso plantado", collections=["documentos_clientes"],
        tenant_id=tenant_vitima, score_threshold=0.0,
    )
    assert achados_vitima == [], "conteúdo forjado vazou pro tenant vítima"

    # O conteúdo deve ter ficado carimbado com o tenant do ATACANTE de verdade.
    achados_atacante = await retrieve(
        qdrant_memoria, "conteudo malicioso plantado", collections=["documentos_clientes"],
        tenant_id=tenant_atacante, score_threshold=0.0,
    )
    assert len(achados_atacante) == 1
    assert achados_atacante[0]["payload"]["tenant_id"] == tenant_atacante


async def test_ingest_colecao_publica_nao_exige_tenant_id(qdrant_memoria, monkeypatch):
    """Coleções públicas (jurisprudencia/doutrina/legislacao) não são
    tenant-scoped — o fix não deve forçar/alterar tenant_id nelas."""
    import app.rag.ingestion as ingestion_mod
    import app.api.v1.rag as rag_mod

    async def _fake_get_qdrant():
        return qdrant_memoria

    async def _fake_embed_batch(texts):
        return [[0.03] * settings.EMBEDDING_DIMENSIONS for _ in texts]

    monkeypatch.setattr(ingestion_mod, "get_qdrant", _fake_get_qdrant)
    monkeypatch.setattr(ingestion_mod, "embed_batch", _fake_embed_batch)

    admin = _FakeUser(uuid.uuid4(), str(uuid.uuid4()))
    req = rag_mod.IngestRequest(
        content="texto de doutrina pública",
        collection="doutrina",
        metadata={"autor": "Fulano"},
    )
    resultado = await rag_mod.rag_ingest(req, db=None, current_user=admin)
    assert resultado["chunks_created"] == 1

    ponto = (await qdrant_memoria.scroll(collection_name="doutrina", limit=10))[0][0]
    assert "tenant_id" not in ponto.payload
