"""Fase 4.2 — comparação de qualidade OpenAI (produção) vs BGE-M3 local
(candidato), sob demanda, só para o SUPERADMIN avaliar antes de decidir
avançar para a Fase 4.3 (reindexação real). Nunca toca nas 7 collections
reais do Qdrant — usa uma collection descartável só para o lado BGE-M3
(1024-dim); o lado OpenAI é rankeado por cosseno em memória, sem precisar
de uma 2ª collection de teste (3072-dim) só para isso.
"""
import math

from qdrant_client.models import Distance, PointStruct, VectorParams

from app.db.qdrant import get_qdrant
from app.rag.embeddings import embed_batch, embed_text
from app.rag.embeddings_local import EMBEDDING_DIMENSIONS_LOCAL, embed_batch_local, embed_text_local

TEST_COLLECTION = "_test_bge_m3"


async def comparar_embeddings(queries: list[str], documentos: list[str]) -> dict:
    """Indexa `documentos` nos dois motores e busca cada `query`, devolvendo
    o ranking lado a lado. `queries`/`documentos` devem ser pequenos (uso
    manual, não em lote) — sem limite hardcoded aqui, mas a chamada de
    OpenAI tem custo real por token (modesto para amostras pequenas)."""
    if not queries or not documentos:
        return {"ok": False, "detail": "Informe ao menos 1 query e 1 documento de teste."}

    qdrant = await get_qdrant()

    existing = {c.name for c in (await qdrant.get_collections()).collections}
    if TEST_COLLECTION not in existing:
        await qdrant.create_collection(
            collection_name=TEST_COLLECTION,
            vectors_config=VectorParams(size=EMBEDDING_DIMENSIONS_LOCAL, distance=Distance.COSINE),
        )

    vetores_openai = await embed_batch(documentos)
    vetores_local = await embed_batch_local(documentos)

    pontos = [
        PointStruct(id=i, vector=vetores_local[i], payload={"text": documentos[i]})
        for i in range(len(documentos))
    ]
    await qdrant.upsert(collection_name=TEST_COLLECTION, points=pontos)

    resultados = []
    for query in queries:
        query_vector_local = await embed_text_local(query)
        hits_local = await qdrant.search(
            collection_name=TEST_COLLECTION,
            query_vector=query_vector_local,
            limit=5,
            with_payload=True,
        )
        ranking_local = [{"text": h.payload.get("text", ""), "score": h.score} for h in hits_local]

        query_vector_openai = await embed_text(query)
        ranking_openai = _rank_por_cosseno(query_vector_openai, vetores_openai, documentos)

        resultados.append({
            "query": query,
            "openai": ranking_openai,
            "bge_m3_local": ranking_local,
        })

    return {"ok": True, "resultados": resultados, "collection_teste": TEST_COLLECTION}


def _rank_por_cosseno(query_vec: list[float], doc_vecs: list[list[float]], documentos: list[str]) -> list[dict]:
    def cos_sim(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0

    scored = [(cos_sim(query_vec, doc_vecs[i]), documentos[i]) for i in range(len(documentos))]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"text": text, "score": score} for score, text in scored[:5]]


# ─── Fase 4.3 Parte 1 — reindexar amostra REAL das 7 collections num espaço
# de teste BGE-M3, para validar qualidade contra o corpus de verdade (não só
# amostras digitadas à mão, como o comparar_embeddings acima permite). Nunca
# escreve nas collections reais — só lê (`scroll`), e só grava nas
# descartáveis `_test_bge_m3_{collection}`.
def _test_collection_name(collection_real: str) -> str:
    return f"_test_bge_m3_{collection_real}"


async def reindexar_amostra_teste(collection_real: str, limite: int = 200) -> dict:
    """Lê até `limite` pontos da collection real (só leitura — nunca upsert/
    delete nela) e reindexa o texto via BGE-M3 numa collection de teste
    descartável. Devolve contagem lida/reindexada."""
    from app.rag.collections import COLLECTIONS

    if collection_real not in COLLECTIONS:
        return {"ok": False, "detail": f"Collection desconhecida: {collection_real}"}
    if limite <= 0:
        return {"ok": False, "detail": "limite deve ser positivo"}

    qdrant = await get_qdrant()
    pontos, _ = await qdrant.scroll(
        collection_name=collection_real, limit=limite, with_payload=True, with_vectors=False,
    )
    textos = [p.payload.get("text") for p in pontos if p.payload and p.payload.get("text")]
    if not textos:
        return {
            "ok": False,
            "detail": f"Nenhum ponto com texto encontrado em '{collection_real}' "
                      "(collection vazia ou sem o campo 'text').",
        }

    test_collection = _test_collection_name(collection_real)
    existentes = {c.name for c in (await qdrant.get_collections()).collections}
    if test_collection not in existentes:
        await qdrant.create_collection(
            collection_name=test_collection,
            vectors_config=VectorParams(size=EMBEDDING_DIMENSIONS_LOCAL, distance=Distance.COSINE),
        )

    vetores = await embed_batch_local(textos)
    novos_pontos = [
        PointStruct(id=i, vector=vetores[i], payload={"text": textos[i]})
        for i in range(len(textos))
    ]
    await qdrant.upsert(collection_name=test_collection, points=novos_pontos)

    return {
        "ok": True,
        "collection_origem": collection_real,
        "collection_teste": test_collection,
        "pontos_lidos": len(pontos),
        "pontos_reindexados": len(textos),
    }


async def buscar_teste(collection_real: str, query: str, limite: int = 5) -> dict:
    """Busca `query` (embedada via BGE-M3) na collection de teste já
    reindexada por `reindexar_amostra_teste` — é como o SUPERADMIN avalia a
    qualidade do BGE-M3 contra conteúdo real, sem tocar produção."""
    if not query or not query.strip():
        return {"ok": False, "detail": "Informe uma query."}

    test_collection = _test_collection_name(collection_real)
    qdrant = await get_qdrant()
    existentes = {c.name for c in (await qdrant.get_collections()).collections}
    if test_collection not in existentes:
        return {
            "ok": False,
            "detail": f"Collection de teste '{test_collection}' ainda não existe — "
                      "rode reindexar-test-collection primeiro.",
        }

    query_vector = await embed_text_local(query)
    hits = await qdrant.search(
        collection_name=test_collection, query_vector=query_vector, limit=limite, with_payload=True,
    )
    return {
        "ok": True,
        "collection_teste": test_collection,
        "resultados": [{"text": h.payload.get("text", ""), "score": h.score} for h in hits],
    }
