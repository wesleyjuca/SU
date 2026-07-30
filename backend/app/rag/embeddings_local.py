"""Geração de embeddings via BGE-M3 local (Fase 4.2 — validação em paralelo,
NÃO usado no caminho de produção). `embeddings.py` (OpenAI) continua sendo o
único motor real de `ingestion.py`/`retrieval.py` — este módulo só existe
para o endpoint de comparação `POST /system/brain/embeddings-compare`.

Dimensão de saída: 1024 (BGE-M3), diferente dos 3072 da OpenAI — não é
compatível com as 7 collections reais sem reindexação completa (Fase 4.3).
"""
EMBEDDING_DIMENSIONS_LOCAL = 1024
_MODEL_NAME = "BAAI/bge-m3"

_model = None


def _get_model():
    """Lazy singleton — carrega o modelo (~4,6GB de pesos) na 1ª chamada,
    não no import do módulo, para não pesar o boot do backend."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


async def embed_text_local(text: str) -> list[float]:
    """Retorna embedding de dimensão 1024 para um texto, via BGE-M3 local."""
    text = text.replace("\n", " ").strip()
    if not text:
        return [0.0] * EMBEDDING_DIMENSIONS_LOCAL
    model = _get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


async def embed_batch_local(texts: list[str]) -> list[list[float]]:
    """Gera embeddings para um batch de textos via BGE-M3 local."""
    cleaned = [t.replace("\n", " ").strip() or " " for t in texts]
    model = _get_model()
    vectors = model.encode(cleaned, normalize_embeddings=True)
    return [v.tolist() for v in vectors]
