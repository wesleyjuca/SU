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

    existing = {c.name for c in await qdrant.get_collections()}
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
