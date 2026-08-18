"""Fase 202 (achado ALTO da Fase 201) — `resetar_tenant_demo` apagava só a
linha `Document` do Postgres, nunca os chunks vetoriais no Qdrant nem o
blob no S3. Um documento aprovado no tenant demo ficava indexado no RAG
pra sempre, mesmo depois do "reset diário" supostamente apagar tudo.
Qdrant real em memória (não um Fake), mesmo padrão das Fases 187/198/198.A."""
import uuid

import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct
from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.models.document import Document
from app.models.tenant import Tenant
from app.rag.collections import COLLECTIONS, ensure_collections
from app.services.demo_reset import resetar_tenant_demo

pytestmark = pytest.mark.asyncio


async def _demo_tenant_id(db):
    tenant_id = (await db.execute(
        select(Tenant.id).where(Tenant.slug == "demo", Tenant.is_demo.is_(True))
    )).scalar_one_or_none()
    if tenant_id is None:
        pytest.skip("Seed do tenant demo não disponível neste ambiente")
    return tenant_id


async def test_reset_limpa_chunks_do_qdrant_e_blob_do_s3(monkeypatch):
    async with AsyncSessionLocal() as db:
        demo_id = await _demo_tenant_id(db)
        doc_id = uuid.uuid4()
        db.add(Document(
            id=doc_id, tenant_id=demo_id, tipo="CONTRATO", titulo="Documento de teste — Fase 202",
            conteudo_texto="texto de teste", status="APROVADO",
            arquivo_storage_key=f"documents/{demo_id}/{doc_id}/teste.pdf",
        ))
        await db.commit()

    qdrant = AsyncQdrantClient(location=":memory:")
    await ensure_collections(qdrant)
    config = COLLECTIONS["documentos_clientes"]
    await qdrant.upsert(
        collection_name="documentos_clientes",
        points=[PointStruct(
            id=str(uuid.uuid4()), vector=[0.1] * config["vector_size"],
            payload={"document_id": str(doc_id), "tenant_id": str(demo_id), "text": "chunk de teste"},
        )],
    )

    import app.rag.ingestion as ingestion_module
    async def _fake_get_qdrant():
        return qdrant
    monkeypatch.setattr(ingestion_module, "get_qdrant", _fake_get_qdrant)

    deleted_keys = []
    import app.integrations.object_storage as object_storage_module
    monkeypatch.setattr(object_storage_module, "is_configured", lambda: True)
    async def _fake_delete_bytes(key):
        deleted_keys.append(key)
    monkeypatch.setattr(object_storage_module, "delete_bytes", _fake_delete_bytes)

    from qdrant_client.models import Filter, FieldCondition, MatchValue
    antes = await qdrant.count(
        collection_name="documentos_clientes",
        count_filter=Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=str(doc_id)))]),
    )
    assert antes.count == 1

    async with AsyncSessionLocal() as db:
        await resetar_tenant_demo(db)

    depois = await qdrant.count(
        collection_name="documentos_clientes",
        count_filter=Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=str(doc_id)))]),
    )
    assert depois.count == 0, "reset não limpou os chunks do documento no Qdrant"
    assert deleted_keys == [f"documents/{demo_id}/{doc_id}/teste.pdf"], "reset não chamou object_storage.delete_bytes com a storage_key certa"


async def test_reset_nao_quebra_quando_documento_nao_tem_storage_key(monkeypatch):
    """Documento no caminho legado (base64 inline, sem S3) não deve
    disparar nenhuma chamada de delete no object storage."""
    async with AsyncSessionLocal() as db:
        demo_id = await _demo_tenant_id(db)
        doc_id = uuid.uuid4()
        db.add(Document(
            id=doc_id, tenant_id=demo_id, tipo="CONTRATO", titulo="Documento legado — Fase 202",
            conteudo_texto="", status="RASCUNHO", arquivo_storage_key=None,
        ))
        await db.commit()

    qdrant = AsyncQdrantClient(location=":memory:")
    await ensure_collections(qdrant)
    import app.rag.ingestion as ingestion_module
    async def _fake_get_qdrant():
        return qdrant
    monkeypatch.setattr(ingestion_module, "get_qdrant", _fake_get_qdrant)

    deleted_keys = []
    import app.integrations.object_storage as object_storage_module
    monkeypatch.setattr(object_storage_module, "is_configured", lambda: True)
    async def _fake_delete_bytes(key):
        deleted_keys.append(key)
    monkeypatch.setattr(object_storage_module, "delete_bytes", _fake_delete_bytes)

    async with AsyncSessionLocal() as db:
        resultado = await resetar_tenant_demo(db)

    assert deleted_keys == []
    assert isinstance(resultado["apagados"], dict)
