"""RAG retrieval — busca semântica multi-collection no Qdrant."""
import hashlib
import json
from qdrant_client.models import Filter, FieldCondition, MatchValue, IsEmptyCondition, PayloadField
from app.rag.embeddings import embed_text_with_meta
from app.rag.collections import COLLECTIONS
from app.db.redis import get_redis
import structlog

log = structlog.get_logger()

DEFAULT_COLLECTIONS = ["jurisprudencia", "peticoes_afj", "legislacao"]

# Coleções privadas do escritório: os chunks carregam tenant_id no payload e a
# busca DEVE filtrar por ele (senão um escritório enxerga dados de outro).
# As demais (jurisprudencia, legislacao, doutrina) são bases públicas/compartilhadas.
PRIVATE_COLLECTIONS = {"peticoes_afj", "memorias_afj", "documentos_clientes", "doutrina_privada"}

# Cache de resultado de busca — evita reembedar (OpenAI, pago) + rebuscar no
# Qdrant a mesma query repetida pelo mesmo escritório em janela curta.
CACHE_TTL_SECONDS = 300


def _cache_key(query, collections, filters, k, score_threshold, tenant_id) -> str:
    # tenant_id entra na chave: cache de collection privada nunca pode vazar
    # entre escritórios diferentes.
    payload = {
        "query": query,
        "collections": sorted(collections or []),
        "filters": filters or {},
        "k": k,
        "score_threshold": score_threshold,
        "tenant_id": str(tenant_id) if tenant_id else None,
    }
    raw = json.dumps(payload, sort_keys=True)
    return f"rag:search:{hashlib.sha256(raw.encode()).hexdigest()}"


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

    redis = await get_redis()
    cache_key = None
    if redis:
        cache_key = _cache_key(query, collections, filters, k, score_threshold, tenant_id)
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as exc:
            log.warning("rag_cache_read_failed", error=str(exc))

    # Fase pós-260 (desacoplamento de embeddings de um provedor único) —
    # até 2 vetores da mesma pergunta, já que uma única chamada pode pedir
    # collections públicas e privadas ao mesmo tempo. Collections PÚBLICAS/
    # compartilhadas (jurisprudencia/legislacao/doutrina/documentacao_sistema)
    # sempre resolvem pro provedor PADRÃO da plataforma — a busca pública
    # precisa funcionar pra qualquer tenant, não importa o provedor BYOK
    # dele, já que o conteúdo público foi indexado com um único provedor.
    # Collections PRIVADAS usam o BYOK já ativo no contexto do chamador
    # (mesmo comportamento de antes desta fase).
    alvo = [c for c in collections if c in COLLECTIONS]
    tem_publica = any(c not in PRIVATE_COLLECTIONS for c in alvo)
    tem_privada = any(c in PRIVATE_COLLECTIONS for c in alvo)

    vetor_publico = provider_publico = None
    vetor_privado = provider_privado = None
    if tem_publica:
        vetor_publico, provider_publico, _ = await embed_text_with_meta(query, force_system_default=True)
    if tem_privada:
        vetor_privado, provider_privado, _ = await embed_text_with_meta(query, force_system_default=False)

    all_results = []
    for collection in alvo:
        privada = collection in PRIVATE_COLLECTIONS
        query_vector = vetor_privado if privada else vetor_publico
        provider = provider_privado if privada else provider_publico
        if query_vector is None:
            continue
        # Filtro por coleção: condições do usuário + tenant_id se for
        # privada + provedor de embedding compatível com o vetor de busca.
        extra = {"tenant_id": str(tenant_id)} if (privada and tenant_id) else None
        qdrant_filter = _build_filter(filters, extra, provider)
        try:
            # Fase 187 — `.search()` foi removido do qdrant-client (a versão
            # pinada em requirements.txt, 1.18.0, só tem `.query_points()`,
            # a Query API que substituiu o método antigo). Sem essa troca
            # toda busca aqui caía no `except` abaixo silenciosamente — 200
            # OK com resultado sempre vazio, pra qualquer tenant/coleção.
            response = await qdrant_client.query_points(
                collection_name=collection,
                query=query_vector,
                limit=k,
                query_filter=qdrant_filter,
                with_payload=True,
                score_threshold=score_threshold,
            )
            for hit in response.points:
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
    top_k = all_results[:k]

    if redis and cache_key:
        try:
            await redis.set(cache_key, json.dumps(top_k), ex=CACHE_TTL_SECONDS)
        except Exception as exc:
            log.warning("rag_cache_write_failed", error=str(exc))

    return top_k


def _provider_filter(provider: str) -> Filter:
    """Sub-filtro exigindo que o ponto tenha sido embedado pelo MESMO
    provedor do vetor de busca — embeddings de provedores diferentes não
    são comparáveis por cosseno, mesmo com dimensão idêntica (Fase pós-260).

    Compatibilidade retroativa: todo conteúdo indexado antes desta fase
    nunca gravou `embedding_provider` no payload (só existia OpenAI, nunca
    precisou ser registrado) — tratado aqui como equivalente a "openai",
    senão esse conteúdo desapareceria da busca no dia do deploy.
    """
    condicoes = [FieldCondition(key="embedding_provider", match=MatchValue(value=provider))]
    if provider == "openai":
        condicoes.append(IsEmptyCondition(is_empty=PayloadField(key="embedding_provider")))
    return Filter(should=condicoes)


def _build_filter(
    filters: dict | None, extra: dict | None = None, embedding_provider: str | None = None
) -> Filter | None:
    conditions = []
    for field, value in {**(filters or {}), **(extra or {})}.items():
        conditions.append(FieldCondition(key=field, match=MatchValue(value=value)))
    if embedding_provider:
        conditions.append(_provider_filter(embedding_provider))
    if not conditions:
        return None
    return Filter(must=conditions)
