"""Geração de embeddings via OpenAI text-embedding-3-large."""
from openai import AsyncOpenAI
from app.config import settings

_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


async def embed_text(text: str) -> list[float]:
    """Retorna embedding de dimensão 3072 para um texto."""
    client = get_openai_client()
    text = text.replace("\n", " ").strip()
    if not text:
        return [0.0] * settings.EMBEDDING_DIMENSIONS

    response = await client.embeddings.create(
        input=text,
        model=settings.DEFAULT_EMBEDDING_MODEL,
        dimensions=settings.EMBEDDING_DIMENSIONS,
    )
    return response.data[0].embedding


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Gera embeddings para um batch de textos."""
    client = get_openai_client()
    cleaned = [t.replace("\n", " ").strip() or " " for t in texts]

    response = await client.embeddings.create(
        input=cleaned,
        model=settings.DEFAULT_EMBEDDING_MODEL,
        dimensions=settings.EMBEDDING_DIMENSIONS,
    )
    return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
