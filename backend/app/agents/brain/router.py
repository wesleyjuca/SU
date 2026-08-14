"""Classificação de intent e roteamento de tarefas para agentes."""

TASK_ROUTE_MAP: dict[str, str | list[str]] = {
    # ─── Rotas diretas ────────────────────────────────────────────────────────
    "monitor_process": "process_agent",
    "process_agent": "process_agent",       # alias direto
    "search_by_oab": "process_agent",       # captura por OAB
    "poll_process": "process_agent",        # polling de processo
    "generate_petition": "petition_agent",
    "review_document": "review_agent",
    "search_jurisprudence": "jurisprudence_agent",
    "generate_strategy": "strategy_agent",
    "manage_contract": "contract_agent",
    "ocr_document": "ocr_agent",
    "manage_crm": "crm_agent",
    "financial_report": "financial_agent",
    "marketing_campaign": "marketing_agent",
    "analytics_report": "analytics_agent",
    "visual_law_diagram": "visual_law_agent",
    "visual_law": "visual_law_agent",       # alias (defesa p/ chamadas antigas)
    "audit_review": "audit_agent",
    "compliance_check": "compliance_agent",
    "monitor_court": "court_monitor_agent",
    "monitor_publications": "publication_monitor_agent",
    "generate_code": "coding_agent",
    "innovation_proposal": "innovation_agent",

    # ─── Cadeias multi-agente ─────────────────────────────────────────────────
    "new_process_intake": [
        "process_agent",
        "jurisprudence_agent",
        "strategy_agent",
        "crm_agent",
    ],
    "generate_and_review_petition": [
        "jurisprudence_agent",
        "petition_agent",
        "review_agent",
    ],
    "full_contract_flow": [
        "contract_agent",
        "review_agent",
    ],
}

# Palavras-chave para inferência automática de task_type
INTENT_KEYWORDS: dict[str, list[str]] = {
    "generate_petition": ["petição", "peticao", "recurso", "contestação", "contestacao", "inicial", "memorial"],
    "review_document": ["revisar", "revisão", "revisao", "corrigir", "analisar documento"],
    "search_jurisprudence": ["jurisprudência", "jurisprudencia", "acórdão", "acordao", "precedente", "stj", "stf"],
    "monitor_process": ["monitorar", "andamento", "movimentação", "movimentacao", "processo"],
    "generate_strategy": ["estratégia", "estrategia", "tese", "argumento", "abordagem jurídica"],
    "manage_crm": ["cliente", "lead", "contato", "crm", "captação"],
    "visual_law_diagram": ["fluxograma", "diagrama", "timeline", "visual law", "visualizar"],
}


def get_chain(task_type: str, task_input: dict | None = None) -> list[str]:
    """
    Retorna a cadeia COMPLETA de agentes para a tarefa (1 elemento para
    rotas diretas, N elementos para as chains multi-agente declaradas em
    TASK_ROUTE_MAP). Quem só precisa do primeiro agente deve usar
    classify_task() — get_chain() é a fonte de verdade para o orquestrador
    encadear de verdade (Fase 169.1).
    """
    task_input = task_input or {}

    if task_type == "run_custom_agent":
        return ["custom_agent"]

    if task_type in TASK_ROUTE_MAP:
        route = TASK_ROUTE_MAP[task_type]
        return list(route) if isinstance(route, list) else [route]

    text = (task_input.get("descricao") or task_input.get("query") or "").lower()
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            route = TASK_ROUTE_MAP.get(intent, "orchestration_agent")
            return list(route) if isinstance(route, list) else [route]

    return ["orchestration_agent"]


def classify_task(task_type: str, task_input: dict) -> str:
    """
    Retorna só o primeiro agente da rota/chain para a tarefa — uso legado
    por quem não precisa encadear (ex.: chamadores fora do orquestrador
    LangGraph). O orquestrador em si usa get_chain() para rodar a chain
    inteira, não só o primeiro passo.
    """
    return get_chain(task_type, task_input)[0]
