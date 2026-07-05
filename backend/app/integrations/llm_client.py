"""Camada multi-provider de LLM (Anthropic Claude + Google Gemini).

Todos os agentes chamam `call_claude`, que delega para `call_llm`. O provider
ativo é escolhido por `settings.AI_PROVIDER` (ou pelo argumento `provider`),
permitindo trocar/plugar múltiplas IAs sem alterar nenhum agente.

- anthropic: SDK oficial Anthropic.
- gemini:   endpoint OpenAI-compatível do Google (reusa o SDK `openai` já
            instalado; sem dependência nova).

Retorno padronizado: (content, input_tokens, output_tokens, cost_usd).
"""
import contextvars
from app.config import settings

# Credenciais de IA por-requisição (BYOK). Setado pelo orquestrador com a IA do
# usuário disparador; quando presente, sobrepõe as settings do sistema.
# Formato: {"provider": str, "api_key": str, "model": str | None}
ai_creds_ctx: "contextvars.ContextVar[dict | None]" = contextvars.ContextVar("ai_creds", default=None)

# ─── Preços aproximados por 1M tokens (input/output) ─────────────────────────
MODEL_PRICING = {
    # Anthropic
    "claude-opus-4-7": {"input": 15.0, "output": 75.0},
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

# Cache de clientes por (provider, api_key) — chaves diferem por usuário (BYOK)
_client_cache: dict = {}


def _cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model, {"input": 1.0, "output": 3.0})
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


def resolve_provider(provider: str | None) -> str:
    p = (provider or settings.AI_PROVIDER or "anthropic").lower()
    return "gemini" if p in ("gemini", "google") else "anthropic"


def _default_model(provider: str) -> str:
    return settings.DEFAULT_GEMINI_MODEL if provider == "gemini" else settings.DEFAULT_CLAUDE_MODEL


# ─── Anthropic ───────────────────────────────────────────────────────────────
def _get_anthropic(api_key: str):
    ck = ("anthropic", api_key)
    if ck not in _client_cache:
        import anthropic
        _client_cache[ck] = anthropic.AsyncAnthropic(api_key=api_key)
    return _client_cache[ck]


async def _call_anthropic(api_key, messages, system, model, max_tokens, temperature):
    client = _get_anthropic(api_key)
    kwargs = {"model": model, "max_tokens": max_tokens, "temperature": temperature, "messages": messages}
    if system:
        kwargs["system"] = system
    resp = await client.messages.create(**kwargs)
    content = resp.content[0].text if resp.content else ""
    return content, resp.usage.input_tokens, resp.usage.output_tokens


# ─── Gemini (via endpoint OpenAI-compatível) ─────────────────────────────────
def _get_gemini(api_key: str):
    ck = ("gemini", api_key)
    if ck not in _client_cache:
        from openai import AsyncOpenAI
        _client_cache[ck] = AsyncOpenAI(api_key=api_key, base_url=GEMINI_OPENAI_BASE_URL)
    return _client_cache[ck]


async def _call_gemini(api_key, messages, system, model, max_tokens, temperature):
    client = _get_gemini(api_key)
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
    return content, in_t, out_t


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
    """
    creds = ai_creds_ctx.get()

    if creds and creds.get("api_key"):
        prov = resolve_provider(provider or creds.get("provider"))
        api_key = creds["api_key"]
        mdl = model or creds.get("model") or _default_model(prov)
    else:
        prov = resolve_provider(provider)
        api_key = (settings.GEMINI_API_KEY or settings.OPENAI_API_KEY) if prov == "gemini" else settings.ANTHROPIC_API_KEY
        mdl = model or _default_model(prov)

    if prov == "gemini":
        content, in_t, out_t = await _call_gemini(api_key, messages, system, mdl, max_tokens, temperature)
    else:
        content, in_t, out_t = await _call_anthropic(api_key, messages, system, mdl, max_tokens, temperature)

    return content, in_t, out_t, _cost(mdl, in_t, out_t)
