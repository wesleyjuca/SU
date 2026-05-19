"""API RAG — busca semântica e ingestão de documentos no Qdrant."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.db.base import get_db
from app.dependencies import require_role
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/rag", tags=["rag"])

VALID_COLLECTIONS = {
    "jurisprudencia",
    "peticoes_afj",
    "doutrina",
    "legislacao",
    "memorias_afj",
    "documentos_clientes",
}


class SearchRequest(BaseModel):
    query: str
    collections: list[str] = ["jurisprudencia", "legislacao"]
    k: int = 5
    filters: Optional[dict] = None
    score_threshold: float = 0.5


class IngestRequest(BaseModel):
    content: str
    collection: str
    metadata: dict = {}
    document_id: Optional[str] = None


@router.post("/search")
async def rag_search(
    req: SearchRequest,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "ADVOGADO", "PARALEGAL", "ASSISTENTE")),
):
    invalid = [c for c in req.collections if c not in VALID_COLLECTIONS]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Collections inválidas: {invalid}. Válidas: {sorted(VALID_COLLECTIONS)}",
        )

    if not req.query.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query não pode ser vazia")

    try:
        from app.db.qdrant import get_qdrant_client
        from app.rag.retrieval import retrieve

        qdrant = get_qdrant_client()
        results = await retrieve(
            qdrant_client=qdrant,
            query=req.query,
            collections=req.collections,
            filters=req.filters,
            k=req.k,
            score_threshold=req.score_threshold,
        )
        return {"query": req.query, "collections": req.collections, "results": results, "count": len(results)}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Serviço RAG indisponível: {str(exc)}",
        )


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def rag_ingest(
    req: IngestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    if req.collection not in VALID_COLLECTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Collection inválida: {req.collection}",
        )

    if not req.content.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Conteúdo não pode ser vazio")

    try:
        from app.rag.ingestion import ingest_document

        chunk_ids = await ingest_document(
            content=req.content,
            collection=req.collection,
            metadata={**req.metadata, "ingested_by": str(current_user.id)},
            document_id=req.document_id,
        )
        return {
            "status": "queued",
            "collection": req.collection,
            "chunks_created": len(chunk_ids),
            "chunk_ids": chunk_ids,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Erro na ingestão: {str(exc)}",
        )
