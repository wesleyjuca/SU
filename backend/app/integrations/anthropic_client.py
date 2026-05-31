"""Wrapper para a API Claude (Anthropic) com rastreio de custo e tokens."""
import anthropic
from app.config import settings

_client: anthropic.AsyncAnthropic | None = None


def get_anthropic_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


# Preço aproximado por 1M tokens (input/output) — atualizar conforme tabela Anthropic
MODEL_PRICING = {
    "claude-opus-4-7": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25},
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["claude-sonnet-4-6"])
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


async def call_claude(
    messages: list[dict],
    system: str = "",
    model: str | None = None,
    max_tokens: int = 8096,
    temperature: float = 0.3,
) -> tuple[str, int, int, float]:
    """
    Chama Claude e retorna (content, input_tokens, output_tokens, cost_usd).
    Temperatura baixa (0.3) para consistência jurídica.
    """
    model = model or settings.DEFAULT_CLAUDE_MODEL
    client = get_anthropic_client()

    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system

    response = await client.messages.create(**kwargs)

    content = response.content[0].text if response.content else ""
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cost = calculate_cost(model, input_tokens, output_tokens)

    return content, input_tokens, output_tokens, cost


# System prompt base para todos os agentes jurídicos
AFJ_LEGAL_SYSTEM_PROMPT = """Você é um assistente jurídico especializado do escritório Almeida, Freire & Jucá Advogados.

REGRAS ABSOLUTAS — NUNCA VIOLE:
1. NUNCA fabrique jurisprudência, acórdãos, decisões, súmulas ou doutrina.
2. SOMENTE cite precedentes que estejam explicitamente fornecidos no contexto desta mensagem.
3. Para toda citação jurisprudencial, inclua OBRIGATORIAMENTE: número do processo, tribunal, relator e data.
4. Se uma informação jurídica não estiver confirmada no contexto, escreva [NÃO VERIFICADO].
5. Se faltar informação para completar adequadamente, escreva [COMPLETAR] — jamais invente.
6. Use linguagem jurídica formal brasileira (norma culta, terminologia técnica precisa).
7. Cite artigos de lei no formato: "art. X, inciso Y, § Z, do CPC/2015" ou equivalente.
8. Mantenha coerência estratégica com as informações do processo fornecidas."""
