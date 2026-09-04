"""Pipeline de ingestão de documentos para Qdrant."""
from uuid import uuid4
from typing import Optional
import hashlib
import structlog

from app.rag.embeddings import embed_batch_with_meta
from app.rag.chunker import chunk_document
from app.db.qdrant import get_qdrant
from qdrant_client.models import PointStruct

log = structlog.get_logger()


async def ingest_document(
    content: str,
    collection: str,
    metadata: dict,
    document_id: Optional[str] = None,
    force_system_default: bool = False,
) -> list[str]:
    """Ingere um documento na collection Qdrant. Retorna IDs dos pontos inseridos.

    `force_system_default` — Fase pós-260: quando `True` (usado pras 3
    collections PÚBLICAS/compartilhadas — jurisprudência, legislação,
    doutrina —, nunca deve depender de qual admin específico disparou a
    ingestão), ignora o BYOK do usuário e usa sempre o provedor de
    embedding padrão do sistema. `False` (default, usado pras collections
    PRIVADAS por tenant) usa o BYOK já ativo no contexto do chamador, mesmo
    padrão de todo o resto do sistema."""
    chunks = chunk_document(content, metadata)
    if not chunks:
        return []

    texts = [c["text"] for c in chunks]
    embeddings, provider, model = await embed_batch_with_meta(
        texts, force_system_default=force_system_default
    )

    points = []
    point_ids = []
    for chunk, embedding in zip(chunks, embeddings):
        point_id = str(uuid4())
        point_ids.append(point_id)
        payload = {
            **metadata,
            "text": chunk["text"],
            "chunk_index": chunk["index"],
            "chunk_total": chunk["total"],
            "content_hash": hashlib.sha256(chunk["text"].encode()).hexdigest()[:16],
            # Fase pós-260 — provedor/modelo REAL usado pra gerar este
            # vetor, nunca assumido. Base pro filtro de compatibilidade
            # em retrieval.py (pontos sem este campo = "openai" por
            # compat retroativa).
            "embedding_provider": provider,
            "embedding_model": model,
        }
        if document_id:
            payload["document_id"] = document_id
        points.append(PointStruct(id=point_id, vector=embedding, payload=payload))

    client = await get_qdrant()
    await client.upsert(collection_name=collection, points=points)

    log.info(
        "rag_ingested",
        collection=collection,
        chunks=len(points),
        document_id=document_id,
        embedding_provider=provider,
    )
    return point_ids


async def delete_document_chunks(collection: str, document_id: str) -> None:
    """Remove todos os chunks de um documento da collection."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    client = await get_qdrant()
    await client.delete(
        collection_name=collection,
        points_selector=Filter(
            must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
        ),
    )
    log.info("rag_deleted", collection=collection, document_id=document_id)
