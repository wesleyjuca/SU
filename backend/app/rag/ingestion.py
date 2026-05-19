"""Pipeline de ingestão de documentos para Qdrant."""
from pathlib import Path
from uuid import uuid4
from typing import Optional
import hashlib
import structlog

from app.rag.embeddings import embed_batch
from app.rag.chunker import chunk_document
from app.db.qdrant import get_qdrant_client
from qdrant_client.models import PointStruct

log = structlog.get_logger()


async def ingest_document(
    content: str,
    collection: str,
    metadata: dict,
    document_id: Optional[str] = None,
) -> list[str]:
    """Ingere um documento na collection Qdrant. Retorna IDs dos pontos inseridos."""
    chunks = chunk_document(content, metadata)
    if not chunks:
        return []

    texts = [c["text"] for c in chunks]
    embeddings = await embed_batch(texts)

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
        }
        if document_id:
            payload["document_id"] = document_id
        points.append(PointStruct(id=point_id, vector=embedding, payload=payload))

    client = await get_qdrant_client()
    await client.upsert(collection_name=collection, points=points)

    log.info("rag_ingested", collection=collection, chunks=len(points), document_id=document_id)
    return point_ids


async def delete_document_chunks(collection: str, document_id: str) -> None:
    """Remove todos os chunks de um documento da collection."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    client = await get_qdrant_client()
    await client.delete(
        collection_name=collection,
        points_selector=Filter(
            must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
        ),
    )
    log.info("rag_deleted", collection=collection, document_id=document_id)
