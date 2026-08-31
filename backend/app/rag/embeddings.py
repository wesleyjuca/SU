"""Geração de embeddings via OpenAI text-embedding-3-large."""
from openai import AsyncOpenAI
from app.config import settings

_client: AsyncOpenAI | None = None


def _resolve_byok_openai_key() -> tuple[str | None, str | None]:
    """Fase 255 — se o usuário disparador tem BYOK ativo com provider
    "openai" (setado por `user_ai_creds()`, mesmo contextvar que
    `call_llm` já usa), reaproveita essa chave pra embeddings: é a mesma
    API OpenAI, a mesma chave já serve completions e embeddings. Provider
    diferente de "openai" (Anthropic/Gemini/...) não gera embedding
    compatível com as collections existentes — ignorado de propósito."""
    try:
        from app.integrations.llm_client import ai_creds_ctx
        creds = ai_creds_ctx.get()
    except LookupError:
        creds = None
    if creds and creds.get("provider") == "openai" and creds.get("api_key"):
        return creds["api_key"], creds.get("base_url") or None
    return None, None


def get_openai_client() -> AsyncOpenAI:
    byok_key, byok_base_url = _resolve_byok_openai_key()
    if byok_key:
        # Credencial BYOK varia por usuário — nunca cacheada no singleton
        # global (mesmo padrão de `_call_openai_compatible` em llm_client.py).
        return AsyncOpenAI(api_key=byok_key, base_url=byok_base_url)

    global _client
    if _client is None:
        if not settings.OPENAI_API_KEY:
            # A busca vetorial depende de embeddings da OpenAI. Sem chave de
            # sistema nem BYOK do usuário, falha com mensagem clara (em vez
            # de um 401 genérico).
            raise RuntimeError(
                "Busca vetorial indisponível: OPENAI_API_KEY não configurada. "
                "Configure a chave OpenAI do sistema, ou configure sua "
                "própria chave OpenAI em \"Minha IA\" para habilitar "
                "embeddings."
            )
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
