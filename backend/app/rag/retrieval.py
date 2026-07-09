"""RAG retrieval — busca semântica multi-collection no Qdrant."""
from qdrant_client.models import Filter, FieldCondition, MatchValue
from app.rag.embeddings import embed_text
from app.rag.collections import COLLECTIONS
import structlog

log = structlog.get_logger()

DEFAULT_COLLECTIONS = ["jurisprudencia", "peticoes_afj", "legislacao"]

# Coleções privadas do escritório: os chunks carregam tenant_id no payload e a
# busca DEVE filtrar por ele (senão um escritório enxerga dados de outro).
# As demais (jurisprudencia, legislacao, doutrina) são bases públicas/compartilhadas.
PRIVATE_COLLECTIONS = {"peticoes_afj", "memorias_afj", "documentos_clientes"}


async def retrieve(
    qdrant_client,
    query: str,
    collections: list[str] | None = None,
    filters: dict | None = None,
    k: int = 5,
    score_threshold: float = 0.35,  # threshold permissivo p/ documentos jurídicos
    tenant_id=None,
) -> list[dict]:
    """
    Busca semântica multi-collection.
    Retorna lista de chunks com text, score e payload.
    Todos os resultados incluem metadados de fonte para rastreabilidade.

    Isolamento multi-tenant: nas coleções privadas do escritório o filtro por
    tenant_id é aplicado automaticamente; nas públicas, não.
    """
    if not query.strip():
        return []

    collections = collections or DEFAULT_COLLECTIONS
    query_vector = await embed_text(query)

    all_results = []
    for collection in collections:
        if collection not in COLLECTIONS:
            continue
        # Filtro por coleção: condições do usuário + tenant_id se for privada.
        extra = {"tenant_id": str(tenant_id)} if (collection in PRIVATE_COLLECTIONS and tenant_id) else None
        qdrant_filter = _build_filter(filters, extra)
        try:
            hits = await qdrant_client.search(
                collection_name=collection,
                query_vector=query_vector,
                limit=k,
                query_filter=qdrant_filter,
                with_payload=True,
                score_threshold=score_threshold,
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


def _build_filter(filters: dict | None, extra: dict | None = None) -> Filter | None:
    conditions = []
    for field, value in {**(filters or {}), **(extra or {})}.items():
        conditions.append(FieldCondition(key=field, match=MatchValue(value=value)))
    if not conditions:
        return None
    return Filter(must=conditions)
