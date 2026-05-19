"""RAG retrieval — busca semântica multi-collection no Qdrant."""
from qdrant_client.models import Filter, FieldCondition, MatchValue
from app.rag.embeddings import embed_text
from app.rag.collections import COLLECTIONS
import structlog

log = structlog.get_logger()

DEFAULT_COLLECTIONS = ["jurisprudencia", "peticoes_afj", "legislacao"]


async def retrieve(
    qdrant_client,
    query: str,
    collections: list[str] | None = None,
    filters: dict | None = None,
    k: int = 5,
) -> list[dict]:
    """
    Busca semântica multi-collection.
    Retorna lista de chunks com text, score e payload.
    Todos os resultados incluem metadados de fonte para rastreabilidade.
    """
    if not query.strip():
        return []

    collections = collections or DEFAULT_COLLECTIONS
    query_vector = await embed_text(query)

    qdrant_filter = _build_filter(filters) if filters else None

    all_results = []
    for collection in collections:
        if collection not in COLLECTIONS:
            continue
        try:
            hits = await qdrant_client.search(
                collection_name=collection,
                query_vector=query_vector,
                limit=k,
                query_filter=qdrant_filter,
                with_payload=True,
                score_threshold=0.6,  # descartar resultados de baixa relevância
            )
            for hit in hits:
                all_results.append({
                    "collection": collection,
                    "score": hit.score,
                    "text": hit.payload.get("text", ""),
                    "payload": hit.payload,
                    "id": str(hit.id),
                })
        except Exception as exc:
            log.warning("qdrant_search_failed", collection=collection, error=str(exc))

    # Ordenar por score decrescente, retornar top-k
    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:k]


def _build_filter(filters: dict) -> Filter | None:
    conditions = []
    for field, value in filters.items():
        conditions.append(FieldCondition(key=field, match=MatchValue(value=value)))
    if not conditions:
        return None
    return Filter(must=conditions)
