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


def classify_task(task_type: str, task_input: dict) -> str:
    """
    Retorna a rota (nome do agente ou chain) para a tarefa.
    Se task_type já mapeado diretamente, usa ele.
    Caso contrário, tenta inferir por palavras-chave no task_input.
    """
    if task_type in TASK_ROUTE_MAP:
        route = TASK_ROUTE_MAP[task_type]
        # Para chains, retorna o primeiro agente (orquestrador encadeia)
        return route[0] if isinstance(route, list) else route

    # Inferência por palavras-chave
    text = (task_input.get("descricao") or task_input.get("query") or "").lower()
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            route = TASK_ROUTE_MAP.get(intent, "orchestration_agent")
            return route[0] if isinstance(route, list) else route

    return "orchestration_agent"
