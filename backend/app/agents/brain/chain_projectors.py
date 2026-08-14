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


def _petition_to_review(result: AgentResult, ctx: AgentContext) -> dict:
    """petition_agent (tipo_peticao/citacoes) → review_agent (tipo_documento/
    jurisprudencia_verificada).

    Fase 174.3 — sem esta ponte, review_agent.execute() (que lê
    `task.get("tipo_documento", "PETICAO")` e
    `task.get("jurisprudencia_verificada", [])`) sempre caía nos defaults:
    tratava qualquer petição como "PETICAO" genérica e nunca via nenhuma
    citação como verificada — mesmo as que petition_agent já tinha checado
    via `verificar_citacoes` — fazendo `_etapa_consistencia` marcar toda
    citação real como [NÃO VERIFICADO] (bloqueador ALTA por padrão) e
    `pode_protocolar` ficar sistematicamente False. Como uma ponte custom
    substitui inteiramente o `_default_projector` (que copiaria o output
    bruto), ela também precisa repassar o texto do documento explicitamente
    — senão review_agent recebe `conteudo=""` e falha imediatamente
    ("Conteúdo do documento não fornecido para revisão"). Prioriza
    `conteudo_texto` (a chave usada pela edição humana no momento da
    aprovação — `_aplicar_modificacoes`/`chain_resume.py::_run_remaining_steps`
    mesclam `modifications` por cima do `output` original do passo com gate,
    exatamente sob essa chave) sobre `conteudo` (o texto original gerado
    pela IA) — sem essa prioridade, uma edição humana seria descartada e
    review_agent revisaria o rascunho velho, não o texto que o usuário
    realmente aprovou.
    """
    output = result.output or {}
    overrides: dict = {}
    conteudo = output.get("conteudo_texto") or output.get("conteudo")
    if conteudo:
        overrides["conteudo"] = conteudo
    tipo_peticao = output.get("tipo_peticao")
    if tipo_peticao:
        overrides["tipo_documento"] = tipo_peticao
    citacoes = output.get("citacoes") or []
    verificadas = [
        {"numero": c.get("referencia"), "tribunal": c.get("tribunal") or "N/A"}
        for c in citacoes
        if c.get("status") == "confirmada"
    ]
    if verificadas:
        overrides["jurisprudencia_verificada"] = verificadas
    return overrides


def _contract_to_review(result: AgentResult, ctx: AgentContext) -> dict:
    """contract_agent (tipo/conteudo) → review_agent (tipo_documento/
    conteudo). Mesma prioridade de `conteudo_texto` (edição humana) sobre
    `conteudo` (original da IA) que `_petition_to_review` usa — ver
    docstring lá. Contratos não têm citações a propagar."""
    output = result.output or {}
    overrides: dict = {}
    conteudo = output.get("conteudo_texto") or output.get("conteudo")
    if conteudo:
        overrides["conteudo"] = conteudo
    tipo = output.get("tipo")
    if tipo:
        overrides["tipo_documento"] = tipo
    return overrides


CHAIN_PROJECTORS: dict[tuple[str, str], Bridge] = {
    ("process_agent", "jurisprudence_agent"): _process_to_jurisprudence,
    ("jurisprudence_agent", "strategy_agent"): _jurisprudence_to_strategy,
    ("strategy_agent", "crm_agent"): _strategy_to_crm,
    ("petition_agent", "review_agent"): _petition_to_review,
    ("contract_agent", "review_agent"): _contract_to_review,
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
