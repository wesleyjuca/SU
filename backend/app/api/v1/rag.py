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
    "doutrina_privada",
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


def _para_contrato_publico(results: list[dict]) -> list[dict]:
    """Mapeia o shape interno de retrieve() (text/payload) pro contrato público da API (content/metadata)."""
    return [
        {
            "id": r.get("id"),
            "score": r.get("score"),
            "collection": r.get("collection"),
            "content": r.get("text"),
            "metadata": r.get("payload") or {},
        }
        for r in results
    ]


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
        from app.db.qdrant import get_qdrant
        from app.rag.retrieval import retrieve

        qdrant = await get_qdrant()
        results = await retrieve(
            qdrant_client=qdrant,
            query=req.query,
            collections=req.collections,
            filters=req.filters,
            k=req.k,
            score_threshold=req.score_threshold,
            tenant_id=current_user.tenant_id,  # isola coleções privadas por escritório
        )
        contrato = _para_contrato_publico(results)
        return {"query": req.query, "collections": req.collections, "results": contrato, "count": len(contrato)}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Serviço RAG indisponível: {str(exc)}",
        )


@router.get("/coverage")
async def rag_coverage(
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "ADVOGADO", "PARALEGAL", "ASSISTENTE")),
):
    """Contagem de chunks indexados por coleção (só as públicas — sem detalhe de conteúdo)."""
    try:
        from app.db.qdrant import get_qdrant

        qdrant = await get_qdrant()
        existentes = {c.name for c in (await qdrant.get_collections()).collections}
        colecoes = []
        for nome in sorted(VALID_COLLECTIONS):
            if nome not in existentes:
                colecoes.append({"collection": nome, "pontos": 0})
                continue
            try:
                info = await qdrant.count(collection_name=nome, exact=False)
                colecoes.append({"collection": nome, "pontos": info.count})
            except Exception:
                colecoes.append({"collection": nome, "pontos": None})
        return {"colecoes": colecoes}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Serviço RAG indisponível: {str(exc)}",
        )


@router.get("/jurisprudencia/favorabilidade")
async def rag_jurisprudencia_favorabilidade(
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "ADVOGADO", "PARALEGAL", "ASSISTENTE")),
):
    """Breakdown de favorabilidade por relator na base de jurisprudência STJ
    (Fase 138.5). `tribunal` não entra como eixo — hoje é sempre "STJ" nesta
    coleção (pipeline STJ-only, Fase 138.1). Acórdãos ingeridos antes da
    Fase 138.5 não têm `favoravel` classificado e ficam de fora da contagem."""
    cache_key = "rag:favorabilidade:jurisprudencia"
    try:
        from app.db.redis import get_redis
        import json

        redis = await get_redis()
        if redis:
            cached = await redis.get(cache_key)
            if cached:
                return {"relatores": json.loads(cached)}

        from app.db.qdrant import get_qdrant
        from app.rag.aggregation import agregar_favorabilidade_por_relator

        qdrant = await get_qdrant()
        dados = await agregar_favorabilidade_por_relator(qdrant, "jurisprudencia")

        if redis:
            await redis.set(cache_key, json.dumps(dados), ex=600)
        return {"relatores": dados}
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
