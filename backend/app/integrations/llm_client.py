"""Camada multi-provider de LLM (Anthropic Claude + Google Gemini).

Todos os agentes chamam `call_claude`, que delega para `call_llm`. O provider
ativo é escolhido por `settings.AI_PROVIDER` (ou pelo argumento `provider`),
permitindo trocar/plugar múltiplas IAs sem alterar nenhum agente.

- anthropic: SDK oficial Anthropic.
- gemini:   endpoint OpenAI-compatível do Google (reusa o SDK `openai` já
            instalado; sem dependência nova).

Retorno padronizado: (content, input_tokens, output_tokens, cost_usd).
"""
from app.config import settings

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

_anthropic_client = None
_gemini_client = None


def _cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model, {"input": 1.0, "output": 3.0})
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


def resolve_provider(provider: str | None) -> str:
    p = (provider or settings.AI_PROVIDER or "anthropic").lower()
    return "gemini" if p in ("gemini", "google") else "anthropic"


def _default_model(provider: str) -> str:
    return settings.DEFAULT_GEMINI_MODEL if provider == "gemini" else settings.DEFAULT_CLAUDE_MODEL


# ─── Anthropic ───────────────────────────────────────────────────────────────
def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _anthropic_client


async def _call_anthropic(messages, system, model, max_tokens, temperature):
    client = _get_anthropic()
    kwargs = {"model": model, "max_tokens": max_tokens, "temperature": temperature, "messages": messages}
    if system:
        kwargs["system"] = system
    resp = await client.messages.create(**kwargs)
    content = resp.content[0].text if resp.content else ""
    return content, resp.usage.input_tokens, resp.usage.output_tokens


# ─── Gemini (via endpoint OpenAI-compatível) ─────────────────────────────────
def _get_gemini():
    global _gemini_client
    if _gemini_client is None:
        from openai import AsyncOpenAI
        key = settings.GEMINI_API_KEY or settings.OPENAI_API_KEY
        _gemini_client = AsyncOpenAI(api_key=key, base_url=GEMINI_OPENAI_BASE_URL)
    return _gemini_client


async def _call_gemini(messages, system, model, max_tokens, temperature):
    client = _get_gemini()
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
    """Chama o LLM do provider ativo e retorna (content, input_tokens, output_tokens, cost_usd)."""
    prov = resolve_provider(provider)
    mdl = model or _default_model(prov)

    if prov == "gemini":
        content, in_t, out_t = await _call_gemini(messages, system, mdl, max_tokens, temperature)
    else:
        content, in_t, out_t = await _call_anthropic(messages, system, mdl, max_tokens, temperature)

    return content, in_t, out_t, _cost(mdl, in_t, out_t)
