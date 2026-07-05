"""Interface de IA dos agentes.

`call_claude` é mantido por compatibilidade — hoje delega para a camada
multi-provider (`app.integrations.llm_client`), que roteia para Anthropic
Claude ou Google Gemini conforme `settings.AI_PROVIDER`. Nenhum agente
precisa mudar.
"""
from app.integrations.llm_client import call_llm, MODEL_PRICING, _cost as _calc_cost


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    return _calc_cost(model, input_tokens, output_tokens)


async def call_claude(
    messages: list[dict],
    system: str = "",
    model: str | None = None,
    max_tokens: int = 8096,
    temperature: float = 0.3,
) -> tuple[str, int, int, float]:
    """Chama o LLM do provider ativo e retorna (content, input_tokens, output_tokens, cost_usd).

    O nome é histórico; o provider real é definido por `settings.AI_PROVIDER`
    (anthropic | gemini). Temperatura baixa por padrão para consistência jurídica.
    """
    return await call_llm(
        messages=messages,
        system=system,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
    )


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
