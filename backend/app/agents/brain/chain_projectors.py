"""Projeção de saída→entrada entre passos de uma chain (Fase 169.1).

Nenhum agente lê um campo genérico "saída do agente anterior" — cada
`execute()` só sabe ler as chaves específicas que já espera em
`ctx.task_input` (ex.: `strategy_agent` lê `fatos`/`tipo_acao`,
`jurisprudence_agent` lê `query`/`tese`). Por isso a projeção é
best-effort e por par de agentes, não genérica: cada bridge só PREENCHE
campos que o chamador não tenha informado — o payload original do
trigger sempre vence (ver `project_output`), então uma chain nunca perde
uma instrução explícita do usuário em favor de uma inferência automática.
"""
from typing import Callable

from app.agents.base.result import AgentResult
from app.agents.brain.context import AgentContext

Bridge = Callable[[AgentResult, AgentContext], dict]


def _process_to_jurisprudence(result: AgentResult, ctx: AgentContext) -> dict:
    """process_agent (poll/andamentos) → jurisprudence_agent (query/tese)."""
    output = result.output or {}
    movimentos = output.get("movimentos") or []
    resumos = [
        (m.get("ai_resumo") or m.get("descricao") or "").strip()
        for m in movimentos
        if m.get("ai_resumo") or m.get("descricao")
    ]
    overrides: dict = {}
    query = " | ".join(r for r in resumos[:5] if r)
    if query:
        overrides["query"] = query[:2000]
    return overrides


def _jurisprudence_to_strategy(result: AgentResult, ctx: AgentContext) -> dict:
    """jurisprudence_agent (acórdãos analisados) → strategy_agent (fatos)."""
    output = result.output or {}
    resultados = output.get("resultados") or []
    analise = output.get("analise_ia") or ""
    partes = []
    if analise:
        partes.append(analise[:1500])
    for r in resultados[:3]:
        ementa = (r.get("ementa") or "")[:300]
        if ementa:
            partes.append(f"{r.get('tribunal', '')} — {ementa}")
    overrides: dict = {}
    if partes:
        overrides["fatos"] = "\n\n".join(partes)
    return overrides


def _strategy_to_crm(result: AgentResult, ctx: AgentContext) -> dict:
    """strategy_agent (análise estratégica) → crm_agent (descricao_caso)."""
    output = result.output or {}
    analise = output.get("analise_estrategica") or ""
    overrides: dict = {}
    if analise:
        overrides["descricao_caso"] = analise[:1000]
    overrides.setdefault("action", "analyze_lead")
    return overrides


CHAIN_PROJECTORS: dict[tuple[str, str], Bridge] = {
    ("process_agent", "jurisprudence_agent"): _process_to_jurisprudence,
    ("jurisprudence_agent", "strategy_agent"): _jurisprudence_to_strategy,
    ("strategy_agent", "crm_agent"): _strategy_to_crm,
}


def _default_projector(result: AgentResult, ctx: AgentContext) -> dict:
    return dict(result.output or {})


def project_output(from_agent: str, to_agent: str, result: AgentResult, ctx: AgentContext) -> dict:
    """Devolve o `task_input` do próximo passo: overrides projetados do passo
    anterior + o `task_input` corrente por cima (o corrente sempre vence, seja
    ele o payload original do trigger ou já resultado de uma projeção
    anterior na mesma chain)."""
    bridge = CHAIN_PROJECTORS.get((from_agent, to_agent))
    overrides = bridge(result, ctx) if bridge else _default_projector(result, ctx)
    return {**overrides, **ctx.task_input}
