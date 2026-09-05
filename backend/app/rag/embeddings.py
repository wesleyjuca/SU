"""Geração de embeddings — provedor determinado pela configuração de IA do
usuário (BYOK), com fallback para o padrão do sistema (hoje OpenAI).

Fase pós-260 (desacoplamento de provedor único): generalizado a partir do
que antes só considerava "openai" — qualquer provedor marcado como
"embedding-capable" no registro central (`app.services.ai_providers`,
`embedding_capable_providers()`) é elegível, usando o mesmo cliente
`AsyncOpenAI` (todo provedor com suporte a embeddings hoje expõe um
endpoint compatível com a API da OpenAI — mesmo padrão já usado por
`_call_openai_compatible` em `llm_client.py` pra chat completions).
"""
from openai import AsyncOpenAI

from app.config import settings
from app.services.ai_providers import embedding_capable_providers, get_provider

_client: AsyncOpenAI | None = None


class EmbeddingProviderUnavailable(RuntimeError):
    """Nenhum provedor com suporte a embeddings disponível (nem chave
    central, nem BYOK do usuário). Tipo dedicado (não um `RuntimeError`
    genérico) pra `POST /rag/search` conseguir devolver um campo
    estruturado (`needs_embedding_provider: true`) no corpo do 503, em vez
    de depender de sniffing de texto no frontend."""


def _resolve_embedding_credentials() -> tuple[str | None, str | None, str | None]:
    """Varre a cadeia BYOK do usuário disparador (setada por
    `user_ai_creds()` em `ai_creds_ctx`/`ai_fallback_ctx`, mesmo contextvar
    que `call_llm` já usa) procurando a 1ª credencial de um provedor com
    suporte a embeddings (registro central,
    `ai_providers.embedding_capable_providers()` — hoje openai/gemini).
    Provedor sem suporte (Anthropic/Grok/...) é ignorado de propósito, nunca
    gera embedding compatível com as collections existentes.

    Devolve `(provider, api_key, base_url)` ou `(None, None, None)`.

    Achado real (validação pós-merge da Fase 258/259, preservado aqui):
    a resolução precisa varrer TODA a cadeia de fallback do usuário
    (`ai_fallback_ctx`), não só a config PADRÃO/primária (`ai_creds_ctx`)
    — um usuário com Anthropic como padrão (comum, já que é o provedor do
    resto do sistema) e uma chave de provedor embedding-capable cadastrada
    só como config SECUNDÁRIA nunca teria essa chave considerada se a
    varredura parasse na primária.
    """
    try:
        from app.integrations.llm_client import ai_creds_ctx, ai_fallback_ctx
        primaria = ai_creds_ctx.get()
        fallback = ai_fallback_ctx.get()
    except LookupError:
        primaria = None
        fallback = None
    candidatos = ([primaria] if primaria else []) + (fallback or [])
    capable = embedding_capable_providers()
    for creds in candidatos:
        if creds and creds.get("provider") in capable and creds.get("api_key"):
            return creds["provider"], creds["api_key"], creds.get("base_url") or None
    return None, None, None


def _resolve_byok_openai_key() -> tuple[str | None, str | None]:
    """Compat retroativo — `brain_assistant.py` ainda depende
    especificamente de uma chave OpenAI (sua própria collection/pipeline
    de indexação não foi generalizada nesta fase, fora do escopo
    documentado).

    Varre a MESMA cadeia BYOK (primária + fallback) que
    `_resolve_embedding_credentials()` usa, mas procurando especificamente
    por "openai" — não delega pro resolver genérico, que agora pode achar
    um provedor diferente (ex.: Gemini) antes de chegar numa credencial
    OpenAI mais adiante na cadeia. Mesma assinatura/comportamento de antes
    desta generalização."""
    try:
        from app.integrations.llm_client import ai_creds_ctx, ai_fallback_ctx
        primaria = ai_creds_ctx.get()
        fallback = ai_fallback_ctx.get()
    except LookupError:
        primaria = None
        fallback = None
    candidatos = ([primaria] if primaria else []) + (fallback or [])
    for creds in candidatos:
        if creds and creds.get("provider") == "openai" and creds.get("api_key"):
            return creds["api_key"], creds.get("base_url") or None
    return None, None


def get_embeddings_client(*, force_system_default: bool = False) -> tuple[AsyncOpenAI, str, str, int]:
    """Devolve `(client, provider, model, dimensions)` prontos pra gerar
    embedding.

    Com BYOK resolvido (e `force_system_default=False`, o padrão) usa a
    chave/modelo/dimensão do provedor configurado pelo usuário. Sem BYOK,
    ou com `force_system_default=True` (ex.: ingestão/busca nas
    collections PÚBLICAS/compartilhadas, que precisam do mesmo provedor
    pra qualquer tenant, independente do BYOK de quem disparou a ação),
    cai no padrão do sistema — hoje `settings.OPENAI_API_KEY`, sem mudança
    de comportamento pra quem nunca configurou BYOK.
    """
    if not force_system_default:
        provider, api_key, base_url = _resolve_embedding_credentials()
        if api_key:
            info = get_provider(provider) or {}
            model = info.get("embedding_model") or settings.DEFAULT_EMBEDDING_MODEL
            dimensions = info.get("embedding_dimensions") or settings.EMBEDDING_DIMENSIONS
            # Credencial BYOK varia por usuário — nunca cacheada no
            # singleton global (mesmo padrão de `_call_openai_compatible`
            # em llm_client.py).
            client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            return client, provider, model, dimensions

    global _client
    if _client is None:
        if not settings.OPENAI_API_KEY:
            # Fase 255 preservado, mesmo em force_system_default=True: sem
            # chave central, uma credencial "openai" do usuário disparador
            # (mesmo provedor do padrão da plataforma — semanticamente
            # compatível com o que já foi indexado nas collections
            # públicas) serve de fallback. Nunca aceita outro provedor
            # aqui (ex.: Gemini) — geraria vetor incompatível com o
            # conteúdo público já indexado com OpenAI.
            fallback_key, fallback_base_url = _resolve_byok_openai_key()
            if fallback_key:
                return (
                    AsyncOpenAI(api_key=fallback_key, base_url=fallback_base_url),
                    "openai",
                    settings.DEFAULT_EMBEDDING_MODEL,
                    settings.EMBEDDING_DIMENSIONS,
                )
            provedores = ", ".join(sorted(embedding_capable_providers()))
            raise EmbeddingProviderUnavailable(
                "Busca vetorial indisponível: OPENAI_API_KEY não configurada. "
                "Configure a chave OpenAI do sistema, ou configure sua "
                f"própria chave em \"Minha IA\" (provedores com suporte a "
                f"embeddings hoje: {provedores}) para habilitar a busca."
            )
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client, "openai", settings.DEFAULT_EMBEDDING_MODEL, settings.EMBEDDING_DIMENSIONS


def get_openai_client() -> AsyncOpenAI:
    """Compat retroativo — devolve só o client, sem metadados de provedor."""
    client, _provider, _model, _dimensions = get_embeddings_client()
    return client


async def embed_text_with_meta(
    text: str, *, force_system_default: bool = False
) -> tuple[list[float], str, str]:
    """Retorna `(vetor, provider, model)` para um texto."""
    client, provider, model, dimensions = get_embeddings_client(force_system_default=force_system_default)
    text = text.replace("\n", " ").strip()
    if not text:
        return [0.0] * dimensions, provider, model

    response = await client.embeddings.create(input=text, model=model, dimensions=dimensions)
    return response.data[0].embedding, provider, model


async def embed_batch_with_meta(
    texts: list[str], *, force_system_default: bool = False
) -> tuple[list[list[float]], str, str]:
    """Retorna `(vetores, provider, model)` para um batch de textos."""
    client, provider, model, dimensions = get_embeddings_client(force_system_default=force_system_default)
    cleaned = [t.replace("\n", " ").strip() or " " for t in texts]

    response = await client.embeddings.create(input=cleaned, model=model, dimensions=dimensions)
    vetores = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
    return vetores, provider, model


async def embed_text(text: str) -> list[float]:
    """Retorna embedding para um texto — wrapper fino sobre
    `embed_text_with_meta` (compat retroativo, ex. `embeddings_compare.py`,
    que não precisa do metadado de provedor)."""
    vetor, _provider, _model = await embed_text_with_meta(text)
    return vetor


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Gera embeddings para um batch de textos — wrapper fino sobre
    `embed_batch_with_meta` (compat retroativo, ex. `embeddings_compare.py`)."""
    vetores, _provider, _model = await embed_batch_with_meta(texts)
    return vetores
