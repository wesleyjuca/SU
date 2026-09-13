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

# Achado real de produção (fase pós-264): sem timeout explícito, um lote de
# embedding lento/rate-limitado podia consumir tempo suficiente pra colidir
# com o soft_time_limit da task Celery de sincronização — o sinal
# interrompendo uma chamada de rede assíncrona no meio corrompe o event loop
# ("Event loop is closed" em chamadas seguintes no mesmo processo). Falhar
# rápido e de forma capturável (já existe fail-soft por arquivo no chamador)
# é mais seguro do que depender do timeout implícito (~600s) do SDK.
_EMBEDDING_TIMEOUT_SECONDS = 120.0


class EmbeddingProviderUnavailable(RuntimeError):
    """Nenhum provedor com suporte a embeddings disponível (nem chave
    central, nem BYOK do usuário). Tipo dedicado (não um `RuntimeError`
    genérico) pra `POST /rag/search` conseguir devolver um campo
    estruturado (`needs_embedding_provider: true`) no corpo do 503, em vez
    de depender de sniffing de texto no frontend."""


# Provedor padrão da plataforma. Fica numa constante porque agora é lido em
# dois lugares (aqui e na chave de cache do `retrieve()`) e um divergir do
# outro reintroduz silenciosamente o bug que a chave de cache corrige.
SYSTEM_DEFAULT_PROVIDER = "openai"


def resolve_embedding_provider_name(*, force_system_default: bool = False) -> str:
    """Nome do provedor que `get_embeddings_client()` usaria AGORA, sem
    construir client nem fazer chamada de rede.

    Existe para a chave de cache do `retrieve()`: a chave é montada antes de
    qualquer embedding ser gerado, e sem o provedor nela dois usuários do
    MESMO tenant com BYOK diferente (ex.: um OpenAI, outro Gemini)
    compartilhavam a mesma entrada por 300s — o segundo recebia resultado
    filtrado pelo provedor do primeiro, contradizendo a invariante de
    `_provider_filter()`. Não é vazamento entre escritórios (`tenant_id` já
    está na chave), é resultado errado dentro do mesmo.

    Usa exatamente a mesma resolução de `get_embeddings_client()`, de
    propósito: se as duas divergirem, a chave volta a mentir."""
    if not force_system_default:
        provider, api_key, _base_url = _resolve_embedding_credentials()
        if api_key and provider:
            return provider
    return SYSTEM_DEFAULT_PROVIDER


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
            client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=_EMBEDDING_TIMEOUT_SECONDS)
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
                    AsyncOpenAI(api_key=fallback_key, base_url=fallback_base_url, timeout=_EMBEDDING_TIMEOUT_SECONDS),
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
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=_EMBEDDING_TIMEOUT_SECONDS)
    return _client, SYSTEM_DEFAULT_PROVIDER, settings.DEFAULT_EMBEDDING_MODEL, settings.EMBEDDING_DIMENSIONS


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

    # Client BYOK é criado do zero a cada chamada (nunca o singleton
    # `_client`) — fecha-lo aqui evita o vazamento de recurso; o singleton
    # do provedor padrão NUNCA é fechado aqui (precisa sobreviver entre
    # chamadas do mesmo processo — ver `run_worker_coro`, que o fecha/reseta
    # no fim de cada task, não aqui).
    owns_client = client is not _client
    try:
        response = await client.embeddings.create(input=text, model=model, dimensions=dimensions)
    finally:
        if owns_client:
            await client.close()
    return response.data[0].embedding, provider, model


async def embed_batch_with_meta(
    texts: list[str], *, force_system_default: bool = False
) -> tuple[list[list[float]], str, str]:
    """Retorna `(vetores, provider, model)` para um batch de textos.

    Achado real de produção: a API do Gemini rejeita
    (`BatchEmbedContentsRequest.requests: at most 100 requests can be in
    one batch`, HTTP 400) qualquer chamada com mais de 100 itens — teto
    ausente na API da OpenAI, que aceita a lista inteira de uma vez sem
    fatiar. Diplomas legais inteiros (chunking por artigo, `chunker.py`)
    facilmente passam de 100 chunks. Fatiamento por provedor
    (`embedding_max_batch`, `ai_providers.py`) — `None` preserva o
    comportamento de sempre (1 chamada), um inteiro fatia em lotes
    sequenciais, concatenando os vetores na ordem original de entrada.
    """
    client, provider, model, dimensions = get_embeddings_client(force_system_default=force_system_default)
    cleaned = [t.replace("\n", " ").strip() or " " for t in texts]

    max_batch = (get_provider(provider) or {}).get("embedding_max_batch")
    lotes = (
        [cleaned]
        if not max_batch or len(cleaned) <= max_batch
        else [cleaned[i:i + max_batch] for i in range(0, len(cleaned), max_batch)]
    )

    # Mesmo raciocínio de `embed_text_with_meta` — só fecha o client se ele
    # não for o singleton compartilhado do provedor padrão.
    owns_client = client is not _client
    vetores: list[list[float]] = []
    try:
        for lote in lotes:
            response = await client.embeddings.create(input=lote, model=model, dimensions=dimensions)
            # Achado real de produção: o SDK da OpenAI desserializa a
            # resposta sem validação (`BaseModel.construct()`) — se a API
            # do provedor (a camada de compatibilidade OpenAI do Gemini,
            # confirmado) omitir "index" em algum item, o campo vira `None`
            # em silêncio em vez de erro. `sorted(..., key=lambda x:
            # x.index)` usa `__lt__` internamente e explode com
            # "'<' not supported between instances of 'int' and 'NoneType'"
            # — mensagem críptica que não diz o que aconteceu. Falha alta e
            # explícita aqui: casar um vetor com o chunk de texto errado
            # (se a ordem fosse só presumida) é pior num sistema jurídico
            # do que o arquivo falhar com uma causa clara.
            if any(item.index is None for item in response.data):
                raise RuntimeError(
                    f"Resposta de embedding do provedor '{provider}' veio sem "
                    f"'index' em pelo menos 1 item do lote ({len(response.data)} "
                    "itens) — não é seguro reordenar."
                )
            vetores.extend(item.embedding for item in sorted(response.data, key=lambda x: x.index))
    finally:
        if owns_client:
            await client.close()
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
