"""Registro de slots de prompt editável por agente (Fase 140.1).

Slot "primary" cobre o caso comum: 1 constante de módulo (ou 1 literal
hoisted pra constante) usada em todo(s) o(s) call site(s) do agente. Lista
vazia = agente sem chamada de LLM (lógica determinística) — nada a editar.

crm_agent é a única exceção: dos seus 3 call sites, só o de
`_rascunhar_followup` tem um prompt PRÓPRIO do agente — os outros 2 passam
AFJ_LEGAL_SYSTEM_PROMPT sem nenhuma customização, ou seja, "editar o prompt
do crm_agent" não teria o que sobrescrever ali; editar o
AFJ_LEGAL_SYSTEM_PROMPT global é uma mudança de escopo muito maior (afeta
os 19 agentes) e fica fora desta fase."""

AGENT_PROMPT_SLOTS: dict[str, list[dict]] = {
    # Slot único "primary", 1 constante de módulo usada em todos os call sites
    "jurisprudence_agent": [{"slot": "primary", "label": "Prompt principal"}],
    "petition_agent": [{"slot": "primary", "label": "Prompt principal"}],
    "review_agent": [{"slot": "primary", "label": "Prompt principal (4 etapas compartilham)"}],
    "contract_agent": [{"slot": "primary", "label": "Prompt principal"}],
    "strategy_agent": [{"slot": "primary", "label": "Prompt principal"}],
    "marketing_agent": [{"slot": "primary", "label": "Prompt principal (3 ações compartilham)"}],
    "visual_law_agent": [{"slot": "primary", "label": "Prompt principal (3 ações compartilham)"}],
    "coding_agent": [{"slot": "primary", "label": "Prompt principal"}],
    "innovation_agent": [{"slot": "primary", "label": "Prompt principal"}],
    # Slot único "primary", literal inline hoisted pra constante de módulo
    "compliance_agent": [{"slot": "primary", "label": "Prompt principal (verificação OAB)"}],
    "process_agent": [{"slot": "primary", "label": "Prompt principal (resumo de andamento)"}],
    # Caso especial: só 1 dos 3 call sites tem prompt próprio do agente
    "crm_agent": [{
        "slot": "draft_followup",
        "label": "Follow-up de cliente (único prompt específico do CRM — os outros 2 usam o prompt jurídico base, fora de escopo)",
    }],
    # Sem chamada de LLM — nada editável (lógica determinística)
    "orchestration_agent": [],
    "court_monitor_agent": [],
    "financial_agent": [],
    "audit_agent": [],
    "analytics_agent": [],
    "ocr_agent": [],
    "publication_monitor_agent": [],
}
