"""Camada multi-provider de LLM.

Todos os agentes chamam `call_claude`, que delega para `call_llm`. O provider
ativo é escolhido por `settings.AI_PROVIDER` (ou pelo argumento `provider`,
ou pela IA própria do usuário via BYOK — `ai_creds_ctx`), permitindo trocar/
plugar múltiplas IAs sem alterar nenhum agente.

- anthropic: SDK oficial Anthropic.
- todos os demais (openai/gemini/grok/deepseek/openrouter/ollama): endpoint
  compatível com a API da OpenAI (reusa o SDK `openai` já instalado) — só
  muda `base_url` e se exige chave. Ver `app.services.ai_providers`.

Retorno padronizado: (content, input_tokens, output_tokens, cost_usd).
"""
import asyncio
import contextvars
import time
import anthropic
from openai import (
    APIConnectionError, APITimeoutError, RateLimitError, InternalServerError,
    AuthenticationError as OpenAIAuthenticationError, PermissionDeniedError as OpenAIPermissionDeniedError,
)
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from app.config import settings

# Exceções transientes (rede/timeout/rate-limit/5xx) — únicas que valem retry
# intra-provedor (tentar de novo com a MESMA chave/config). Erros de
# validação/auth nunca se resolvem tentando de novo, então NÃO entram aqui.
_RETRYABLE_ANTHROPIC = (
    anthropic.APIConnectionError, anthropic.APITimeoutError,
    anthropic.RateLimitError, anthropic.InternalServerError,
)
_RETRYABLE_OPENAI = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)

# Retry raso de propósito: BaseAgent.run() já tem seu próprio loop de retry
# (max_retries=2). Um retry profundo aqui componentizaria com aquele (até 3x3
# tentativas numa falha persistente) — isso só absorve blips curtos de rede.
_RETRY_KWARGS = dict(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, min=0.5, max=4), reraise=True)

# Fase 137.3 — gatilho de fallback pra OUTRA config (`ai_fallback_ctx` abaixo):
# além do conjunto retryable intra-provedor, inclui erros de auth/permissão —
# ao contrário de insistir na MESMA chave (inútil), tentar uma config
# DIFERENTE com uma chave diferente faz sentido justamente aqui.
_RETRYABLE_FOR_FALLBACK = _RETRYABLE_ANTHROPIC + _RETRYABLE_OPENAI + (
    anthropic.AuthenticationError, anthropic.PermissionDeniedError,
    OpenAIAuthenticationError, OpenAIPermissionDeniedError,
)

# Credenciais de IA por-requisição (BYOK). Setado pelo orquestrador com a IA do
# usuário disparador; quando presente, sobrepõe as settings do sistema.
# Formato: {"provider": str, "api_key": str, "model": str | None, "base_url": str | None}
# `base_url` só é usado pra provedores sem URL fixa no registro (hoje só
# Ollama, self-hosted) — Fase 137.1.
ai_creds_ctx: "contextvars.ContextVar[dict | None]" = contextvars.ContextVar("ai_creds", default=None)

# Fase 137.3 — demais IAs do usuário (mesmo formato de `ai_creds_ctx`, uma
# lista, em ordem de prioridade), pra `call_llm` tentar automaticamente se a
# de `ai_creds_ctx` falhar de um jeito recuperável. Setado por
# `byok.user_ai_creds()`; vazio/`None` = sem fallback (comportamento de hoje).
# Só usado por `call_llm` — `call_llm_stream` fica fora de escopo (trocar de
# provedor no meio de um stream já em andamento é outro problema).
ai_fallback_ctx: "contextvars.ContextVar[list[dict] | None]" = contextvars.ContextVar("ai_fallback", default=None)

# Fase 130 — sinaliza se a ÚLTIMA chamada de `call_llm` foi cortada por
# limite de tokens (`stop_reason`/`finish_reason` descartado antes desta
# fase — uma petição truncada no meio nunca era detectada, passava pra
# aprovação parecendo completa). Contextvar em vez de mudar a assinatura de
# `call_llm` (usada em dezenas de call sites) — quem se importa lê depois
# do await, sem quebrar ninguém que não olhe pra isso.
last_call_truncated_ctx: "contextvars.ContextVar[bool]" = contextvars.ContextVar("last_call_truncated", default=False)

# Fase 198.B — achado da Fase 197: a Fase 196 implementou streaming dentro
# de `BaseAgent.ask_llm()`, mas nenhum dos 19 agentes chama esse método
# (todos chamam `call_claude`/`call_llm` direto, replicando o bookkeeping
# manualmente desde a Fase 125) — streaming nunca ativava de verdade.
# Setado por `execute_chain_step()` (orchestrator.py) só pra disparo direto
# (chain de 1 passo), lido aqui em `call_llm()` — o ÚNICO ponto que todo
# agente já passa por baixo, sem precisar tocar em nenhum agente
# individual. Formato: {"user_id": str, "run_id": str, "agent_name": str}.
agent_stream_ctx: "contextvars.ContextVar[dict | None]" = contextvars.ContextVar("agent_stream", default=None)

# ─── Preços aproximados por 1M tokens (input/output) ─────────────────────────
MODEL_PRICING = {
    # Anthropic
    "claude-sonnet-5": {"input": 3.0, "output": 15.0},
    "claude-opus-4-8": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25},
    # Google Gemini
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.0},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
}

GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Fase 137.1 — provedores conhecidos (nome canônico + apelidos aceitos).
# "anthropic" usa SDK próprio (_call_anthropic); "vertex_ai" tem branch
# dedicado (_call_vertex_ai, Fase 195 — não é OpenAI-compatível); todos os
# demais passam pelo endpoint OpenAI-compatível genérico (_call_openai_compatible).
_KNOWN_PROVIDERS = {"anthropic", "openai", "gemini", "grok", "deepseek", "openrouter", "ollama", "vertex_ai"}
_PROVIDER_ALIASES = {"google": "gemini", "claude": "anthropic", "xai": "grok"}

# Cache de clientes por (provider, api_key, base_url) — chaves diferem por
# usuário (BYOK) e por provedor (base_url diferente por provedor).
_client_cache: dict = {}


def _cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model, {"input": 1.0, "output": 3.0})
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


def resolve_provider(provider: str | None) -> str:
    """Normaliza o nome do provider. Nome desconhecido cai em 'anthropic'
    (fail-soft, com log) — nunca derruba a chamada por um nome errado."""
    p = (provider or settings.AI_PROVIDER or "anthropic").lower()
    p = _PROVIDER_ALIASES.get(p, p)
    if p in _KNOWN_PROVIDERS:
        return p
    import structlog
    structlog.get_logger().warning("llm_provider_desconhecido", provider=p)
    return "anthropic"


def _default_model(provider: str) -> str:
    from app.services.ai_providers import get_provider
    if provider == "anthropic":
        return settings.DEFAULT_CLAUDE_MODEL
    if provider == "gemini":
        return settings.DEFAULT_GEMINI_MODEL
    info = get_provider(provider)
    return (info or {}).get("modelo_sugerido") or settings.DEFAULT_CLAUDE_MODEL


def _system_api_key(provider: str) -> str:
    """Chave do sistema (sem BYOK) — só configurada pra anthropic/gemini hoje.
    Provedores novos (openai/grok/deepseek/openrouter/ollama) são BYOK-only
    nesta fase — sem chave própria do usuário, a chamada falha com erro de
    auth (esperado, não é um bug: não há chave central pra esses provedores)."""
    if provider == "gemini":
        return settings.GEMINI_API_KEY or settings.OPENAI_API_KEY
    if provider == "anthropic":
        return settings.ANTHROPIC_API_KEY
    return ""


def _provider_base_url(provider: str, custom_base_url: str | None) -> str | None:
    if provider == "gemini":
        return GEMINI_OPENAI_BASE_URL
    from app.services.ai_providers import resolve_base_url
    return resolve_base_url(provider, custom_base_url)


# ─── Anthropic ───────────────────────────────────────────────────────────────
def _get_anthropic(api_key: str):
    ck = ("anthropic", api_key)
    if ck not in _client_cache:
        import anthropic
        _client_cache[ck] = anthropic.AsyncAnthropic(api_key=api_key)
    return _client_cache[ck]


@retry(retry=retry_if_exception_type(_RETRYABLE_ANTHROPIC), **_RETRY_KWARGS)
async def _call_anthropic(api_key, messages, system, model, max_tokens, temperature):
    client = _get_anthropic(api_key)
    kwargs = {"model": model, "max_tokens": max_tokens, "temperature": temperature, "messages": messages}
    if system:
        kwargs["system"] = system
    resp = await client.messages.create(**kwargs)
    content = resp.content[0].text if resp.content else ""
    return content, resp.usage.input_tokens, resp.usage.output_tokens, resp.stop_reason


# ─── Endpoint OpenAI-compatível genérico (gemini/openai/grok/deepseek/ ───────
# ─── openrouter/ollama — todos expõem essa API, só muda base_url/chave) ──────
def _get_openai_compatible(base_url: str, api_key: str):
    ck = ("openai_compat", base_url, api_key)
    if ck not in _client_cache:
        from openai import AsyncOpenAI
        # Ollama (auth_method="none") não exige chave — o SDK openai exige uma
        # string não-vazia pra instanciar o client; qualquer valor serve.
        _client_cache[ck] = AsyncOpenAI(api_key=api_key or "not-needed", base_url=base_url)
    return _client_cache[ck]


@retry(retry=retry_if_exception_type(_RETRYABLE_OPENAI), **_RETRY_KWARGS)
async def _call_openai_compatible(base_url, api_key, messages, system, model, max_tokens, temperature):
    client = _get_openai_compatible(base_url, api_key)
    # OpenAI-compat: system vira uma mensagem role=system no início
    oai_messages = ([{"role": "system", "content": system}] if system else []) + list(messages)
    resp = await client.chat.completions.create(
        model=model,
        messages=oai_messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    content = resp.choices[0].message.content or ""
    usage = resp.usage
    in_t = getattr(usage, "prompt_tokens", 0) if usage else 0
    out_t = getattr(usage, "completion_tokens", 0) if usage else 0
    finish_reason = resp.choices[0].finish_reason if resp.choices else None
    return content, in_t, out_t, finish_reason


# ─── Google Vertex AI (Fase 195) — BYOK via conta de serviço do próprio ──────
# ─── projeto GCP do escritório, não é OpenAI-compatível ──────────────────────
_VERTEX_TOKEN_URL = "https://oauth2.googleapis.com/token"
_VERTEX_DEFAULT_LOCATION = "us-central1"


async def _vertex_access_token(sa: dict) -> str:
    """Troca a conta de serviço (JSON colado como `api_key` na config BYOK)
    por um access_token OAuth2 de curta duração via o fluxo JWT Bearer do
    Google (RFC 7523) — cacheado em `_client_cache` até pouco antes de expirar.
    Nunca usa o SDK google-cloud-aiplatform (não é dependência deste projeto,
    ver README de app/integrations/) — REST puro via httpx, mesmo padrão de
    todas as outras integrações Google já existentes (google_workspace.py)."""
    ck = ("vertex_token", sa.get("client_email"), sa.get("private_key_id"))
    cached = _client_cache.get(ck)
    if cached and cached[1] > time.time() + 30:
        return cached[0]

    import jwt as pyjwt
    import httpx

    now = int(time.time())
    assertion = pyjwt.encode(
        {
            "iss": sa["client_email"],
            "scope": "https://www.googleapis.com/auth/cloud-platform",
            "aud": _VERTEX_TOKEN_URL,
            "iat": now,
            "exp": now + 3600,
        },
        sa["private_key"],
        algorithm="RS256",
    )
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(_VERTEX_TOKEN_URL, data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        })
    if resp.status_code >= 400:
        raise RuntimeError(f"Vertex AI recusou a conta de serviço ({resp.status_code}): {resp.text[:300]}")
    data = resp.json()
    token = data["access_token"]
    _client_cache[ck] = (token, time.time() + data.get("expires_in", 3600))
    return token


@retry(retry=retry_if_exception_type(_RETRYABLE_OPENAI), **_RETRY_KWARGS)
async def _call_vertex_ai(service_account_json, location, messages, system, model, max_tokens, temperature):
    import json

    try:
        sa = json.loads(service_account_json)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Credencial do Vertex AI inválida — cole o JSON completo da conta de serviço.") from exc
    project_id = sa.get("project_id")
    if not project_id or not sa.get("client_email") or not sa.get("private_key"):
        raise RuntimeError("JSON da conta de serviço incompleto (faltam project_id/client_email/private_key).")

    loc = (location or "").strip() or _VERTEX_DEFAULT_LOCATION
    token = await _vertex_access_token(sa)

    contents = [
        {"role": "model" if m.get("role") == "assistant" else "user", "parts": [{"text": m.get("content", "")}]}
        for m in messages
    ]
    body = {"contents": contents, "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    import httpx
    url = (
        f"https://{loc}-aiplatform.googleapis.com/v1/projects/{project_id}"
        f"/locations/{loc}/publishers/google/models/{model}:generateContent"
    )
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(url, headers={"Authorization": f"Bearer {token}"}, json=body)
    if resp.status_code >= 400:
        raise RuntimeError(f"Vertex AI recusou a chamada ({resp.status_code}): {resp.text[:300]}")

    data = resp.json()
    candidates = data.get("candidates") or []
    parts = (candidates[0].get("content", {}).get("parts") or []) if candidates else []
    content = "".join(p.get("text", "") for p in parts)
    usage = data.get("usageMetadata") or {}
    in_t, out_t = usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0)
    finish_reason = candidates[0].get("finishReason") if candidates else None
    return content, in_t, out_t, finish_reason


def _resolve_call_params(creds: dict | None, provider: str | None, model: str | None):
    """Resolve (prov, api_key, mdl, base_url, config_id) a partir de um dict de
    credenciais (formato de `ai_creds_ctx`/entradas de `ai_fallback_ctx`) ou das
    settings do sistema quando `creds` é `None`. Reusado pelo candidato
    principal e por cada entrada da cadeia de fallback (Fase 137.3).
    `config_id` (Fase 137.7 — monitoramento por IA) vem do próprio dict de
    credenciais (setado por `byok.py`); `None` quando não há BYOK/config.

    `creds is not None` (não `creds.get("api_key")`) decide se há BYOK: uma
    config Ollama (`auth_method="none"`) tem `api_key=""` de propósito — checar
    truthiness da chave descartaria essas configs silenciosamente."""
    if creds is not None:
        prov = resolve_provider(provider or creds.get("provider"))
        api_key = creds.get("api_key") or ""
        mdl = model or creds.get("model") or _default_model(prov)
        return prov, api_key, mdl, _provider_base_url(prov, creds.get("base_url")), creds.get("config_id")
    prov = resolve_provider(provider)
    mdl = model or _default_model(prov)
    return prov, _system_api_key(prov), mdl, _provider_base_url(prov, None), None


# ─── Entrada unificada ───────────────────────────────────────────────────────
async def call_llm(
    messages: list[dict],
    system: str = "",
    model: str | None = None,
    max_tokens: int = 8096,
    temperature: float = 0.3,
    provider: str | None = None,
) -> tuple[str, int, int, float]:
    """Chama o LLM e retorna (content, input_tokens, output_tokens, cost_usd).

    Credenciais (BYOK): se o contextvar `ai_creds_ctx` estiver setado (IA do
    usuário logado), usa provider/chave/modelo dele; senão usa as settings do
    sistema. Assim a chave do usuário economiza os tokens/custo central.

    Fallback (Fase 137.3): se a chamada falhar de um jeito recuperável (rede/
    timeout/rate-limit/5xx/auth) e houver outras IAs do usuário em
    `ai_fallback_ctx` (setado por `byok.user_ai_creds()`, ordenadas por
    prioridade), tenta a próxima automaticamente antes de desistir.

    Monitoramento (Fase 137.7): cada tentativa com uma `AIProviderConfig`
    conhecida (sucesso ou a falha que disparou o próximo fallback) vira uma
    linha em `AICallLog`, fail-soft — nunca afeta o resultado desta função.

    Streaming (Fase 198.B): se `agent_stream_ctx` estiver setado (disparo
    direto de agente com usuário disparador conhecido — ver
    `orchestrator.py::execute_chain_step`), delega pra `call_llm_stream`
    publicando cada pedaço via WebSocket, mas devolve o MESMO contrato
    `(content, input_tokens, output_tokens, cost_usd)` — transparente pra
    quem chama, sem fallback entre providers (mesma limitação de
    `call_llm_stream`, que já tem seu próprio fallback pra não-streaming
    embutido se o provider falhar antes de emitir qualquer token).
    """
    stream_info = agent_stream_ctx.get()
    if stream_info is not None:
        return await _call_llm_streaming_publish(messages, system, model, max_tokens, temperature, provider, stream_info)

    candidates = [_resolve_call_params(ai_creds_ctx.get(), provider, model)]
    for fb_creds in (ai_fallback_ctx.get() or []):
        candidates.append(_resolve_call_params(fb_creds, provider, model))

    import structlog
    from app.services.ai_monitoring import registrar_chamada_ia
    log = structlog.get_logger()

    for i, (prov, api_key, mdl, base_url, config_id) in enumerate(candidates):
        inicio = time.monotonic()
        try:
            if prov == "anthropic":
                content, in_t, out_t, finish_reason = await _call_anthropic(api_key, messages, system, mdl, max_tokens, temperature)
                last_call_truncated_ctx.set(finish_reason == "max_tokens")
            elif prov == "vertex_ai":
                content, in_t, out_t, finish_reason = await _call_vertex_ai(api_key, base_url, messages, system, mdl, max_tokens, temperature)
                last_call_truncated_ctx.set(finish_reason == "MAX_TOKENS")
            else:
                content, in_t, out_t, finish_reason = await _call_openai_compatible(base_url, api_key, messages, system, mdl, max_tokens, temperature)
                last_call_truncated_ctx.set(finish_reason == "length")
            cost = _cost(mdl, in_t, out_t)
            await registrar_chamada_ia(
                config_id, prov, mdl, True, None, in_t, out_t, cost,
                int((time.monotonic() - inicio) * 1000),
            )
            return content, in_t, out_t, cost
        except _RETRYABLE_FOR_FALLBACK as exc:
            await registrar_chamada_ia(
                config_id, prov, mdl, False, str(exc), 0, 0, 0.0,
                int((time.monotonic() - inicio) * 1000),
            )
            if i < len(candidates) - 1:
                log.warning("llm_fallback_provider", de=prov, para=candidates[i + 1][0])
                continue
            if len(candidates) > 1:
                log.warning("ai_fallback_config_esgotado", tentativas=len(candidates))
            raise


async def _call_llm_streaming_publish(
    messages: list[dict], system: str, model: str | None, max_tokens: int,
    temperature: float, provider: str | None, stream_info: dict,
) -> tuple[str, int, int, float]:
    """Fase 198.B — consome `call_llm_stream`, publica cada pedaço via
    WebSocket (evento AGENT_RUN_DELTA) e devolve o texto acumulado no
    mesmo formato que `call_llm` devolveria. Limpa `agent_stream_ctx`
    ANTES de iterar `call_llm_stream` — se o provider falhar antes de
    emitir qualquer token, `call_llm_stream` cai pro seu próprio fallback
    não-streaming chamando `call_llm(...)` de novo; sem limpar o
    contextvar aqui, essa chamada interna cairia de novo neste mesmo
    branch (recursão infinita)."""
    from app.api.v1.ws import publish_event

    token = agent_stream_ctx.set(None)
    try:
        parts: list[str] = []
        tokens_in = tokens_out = 0
        cost = 0.0
        async for kind, val in call_llm_stream(
            messages=messages, system=system, model=model,
            max_tokens=max_tokens, temperature=temperature, provider=provider,
        ):
            if kind == "delta":
                parts.append(val)
                await publish_event(stream_info["user_id"], "AGENT_RUN_DELTA", {
                    "run_id": stream_info["run_id"], "agent_name": stream_info["agent_name"], "delta": val,
                })
            elif kind == "done":
                tokens_in = val.get("input_tokens", 0)
                tokens_out = val.get("output_tokens", 0)
                cost = val.get("cost_usd", 0.0)
        return "".join(parts), tokens_in, tokens_out, cost
    finally:
        agent_stream_ctx.reset(token)


# ─── Comparação/consenso entre configs (Fase 137.5) ──────────────────────────
async def _call_with_config(
    config: dict, messages: list[dict], system: str = "",
    max_tokens: int = 2048, temperature: float = 0.3,
) -> dict:
    """Chama UMA config explicitamente (sem contextvar) — usada por
    `call_llm_parallel`, onde não existe "a config ativa da requisição":
    existem N configs concorrentes de propósito. Nunca propaga exceção —
    devolve `error` preenchido na própria entrada, pra 1 config falhando
    não derrubar as outras do `asyncio.gather`. Também loga em `AICallLog`
    (Fase 137.7), fail-soft, se `config` tiver um `config_id`."""
    from app.services.ai_monitoring import registrar_chamada_ia

    inicio = time.monotonic()
    prov, api_key, mdl, base_url, config_id = _resolve_call_params(config, None, None)
    try:
        if prov == "anthropic":
            content, in_t, out_t, _finish = await _call_anthropic(api_key, messages, system, mdl, max_tokens, temperature)
        elif prov == "vertex_ai":
            content, in_t, out_t, _finish = await _call_vertex_ai(api_key, base_url, messages, system, mdl, max_tokens, temperature)
        else:
            content, in_t, out_t, _finish = await _call_openai_compatible(base_url, api_key, messages, system, mdl, max_tokens, temperature)
        latency_ms = int((time.monotonic() - inicio) * 1000)
        cost = _cost(mdl, in_t, out_t)
        await registrar_chamada_ia(config_id, prov, mdl, True, None, in_t, out_t, cost, latency_ms)
        return {
            "provider": prov, "model": mdl, "content": content,
            "input_tokens": in_t, "output_tokens": out_t,
            "cost_usd": cost, "latency_ms": latency_ms, "error": None,
        }
    except Exception as exc:
        latency_ms = int((time.monotonic() - inicio) * 1000)
        erro = str(exc)[:300]
        await registrar_chamada_ia(config_id, prov, mdl, False, erro, 0, 0, 0.0, latency_ms)
        return {
            "provider": prov, "model": mdl, "content": None,
            "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
            "latency_ms": latency_ms, "error": erro,
        }


async def call_llm_parallel(
    configs: list[dict], messages: list[dict], system: str = "",
    max_tokens: int = 2048, temperature: float = 0.3,
) -> list[dict]:
    """Chama N configs em paralelo pra comparação/consenso (Fase 137.5) — cada
    `config` é um dict no formato de `ai_creds_ctx`. Devolve a lista na MESMA
    ordem recebida; cada entrada nunca lança — `_call_with_config` já captura
    o próprio erro, então 1 config falhando não derruba as demais."""
    return await asyncio.gather(*[
        _call_with_config(config, messages, system, max_tokens, temperature)
        for config in configs
    ])


def _resolve_creds(provider, model):
    """Resolve (prov, api_key, mdl, base_url) considerando BYOK — usado só por
    `call_llm_stream`, que fica de fora do fallback da Fase 137.3 e do
    monitoramento por IA da Fase 137.7 (trocar de provedor/logar no meio de um
    stream já em andamento é outro problema) — por isso descarta `config_id`."""
    prov, api_key, mdl, base_url, _config_id = _resolve_call_params(ai_creds_ctx.get(), provider, model)
    return prov, api_key, mdl, base_url


async def call_llm_stream(
    messages: list[dict],
    system: str = "",
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    provider: str | None = None,
):
    """Gerador assíncrono para chat com streaming de tokens.

    Emite tuplas ("delta", texto) conforme os tokens chegam e, ao final,
    ("done", {input_tokens, output_tokens, cost_usd}). Se o provider falhar
    ANTES de emitir qualquer token, cai para uma chamada não-streaming
    (evita resposta vazia); se falhar no meio, encerra com o que já saiu."""
    prov, api_key, mdl, base_url = _resolve_creds(provider, model)
    emitido = False
    try:
        if prov == "vertex_ai":
            # Fase 195 — sem streaming nativo nesta fase (a Query API do
            # Vertex suporta streamGenerateContent, mas é escopo novo); cai
            # direto pro caminho não-streaming em vez de tentar montar um
            # client OpenAI-compatível com `base_url` que aqui é uma REGIÃO
            # do GCP, não uma URL — daria erro de conexão sem sentido.
            content, in_t, out_t, cost = await call_llm(messages, system, model, max_tokens, temperature, provider)
            yield ("delta", content)
            yield ("done", {"input_tokens": in_t, "output_tokens": out_t, "cost_usd": cost, "fallback": True})
            return
        if prov != "anthropic":
            client = _get_openai_compatible(base_url, api_key)
            oai_messages = ([{"role": "system", "content": system}] if system else []) + list(messages)
            stream = await client.chat.completions.create(
                model=mdl, messages=oai_messages, max_tokens=max_tokens,
                temperature=temperature, stream=True, stream_options={"include_usage": True},
            )
            in_t = out_t = 0
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    emitido = True
                    yield ("delta", chunk.choices[0].delta.content)
                if getattr(chunk, "usage", None):
                    in_t = getattr(chunk.usage, "prompt_tokens", 0) or 0
                    out_t = getattr(chunk.usage, "completion_tokens", 0) or 0
        else:
            client = _get_anthropic(api_key)
            kwargs = {"model": mdl, "max_tokens": max_tokens, "temperature": temperature, "messages": messages}
            if system:
                kwargs["system"] = system
            in_t = out_t = 0
            async with client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    emitido = True
                    yield ("delta", text)
                final = await stream.get_final_message()
                in_t, out_t = final.usage.input_tokens, final.usage.output_tokens
        yield ("done", {"input_tokens": in_t, "output_tokens": out_t, "cost_usd": _cost(mdl, in_t, out_t)})
    except Exception:
        if not emitido:
            content, in_t, out_t, cost = await call_llm(messages, system, model, max_tokens, temperature, provider)
            yield ("delta", content)
            yield ("done", {"input_tokens": in_t, "output_tokens": out_t, "cost_usd": cost, "fallback": True})
        else:
            yield ("done", {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "interrompido": True})
