"""Registro de slots de prompt editável por agente (Fase 140.1).

Slot "primary" cobre o caso comum: 1 constante de módulo (ou 1 literal
hoisted pra constante) usada em todo(s) o(s) call site(s) do agente. Lista
vazia = agente sem chamada de LLM (lógica determinística) — nada a editar.

crm_agent é a única exceção: dos seus 3 call sites, só o de
`_rascunhar_followup` tem um prompt PRÓPRIO do agente — os outros 2 passam
AFJ_LEGAL_SYSTEM_PROMPT sem nenhuma customização, ou seja, "editar o prompt
do crm_agent" não teria o que sobrescrever ali; editar o
AFJ_LEGAL_SYSTEM_PROMPT global é uma mudança de escopo muito maior (afeta
os 19 agentes) e fica fora desta fase.

`default_ref` (Fase 140.1.1): caminho pontilhado até a constante Python que
contém o texto padrão desse slot — permite ao endpoint de leitura mostrar o
prompt ATUAL (não só "existe um override ou não"), pra o SUPERADMIN editar a
partir do texto real em vez de uma caixa vazia."""

AGENT_PROMPT_SLOTS: dict[str, list[dict]] = {
    # Slot único "primary", 1 constante de módulo usada em todos os call sites
    "jurisprudence_agent": [{
        "slot": "primary", "label": "Prompt principal",
        "default_ref": "app.agents.jurisprudence.jurisprudence_agent.JURISPRUDENCE_SYSTEM",
    }],
    "petition_agent": [{
        "slot": "primary", "label": "Prompt principal",
        "default_ref": "app.agents.petition.petition_agent.PETITION_SYSTEM_PROMPT",
    }],
    "review_agent": [{
        "slot": "primary", "label": "Prompt principal (4 etapas compartilham)",
        "default_ref": "app.agents.review.review_agent.REVIEW_SYSTEM_PROMPT",
    }],
    "contract_agent": [{
        "slot": "primary", "label": "Prompt principal",
        "default_ref": "app.agents.contract.contract_agent.CONTRACT_SYSTEM",
    }],
    "strategy_agent": [{
        "slot": "primary", "label": "Prompt principal",
        "default_ref": "app.agents.strategy.strategy_agent.STRATEGY_SYSTEM",
    }],
    "marketing_agent": [{
        "slot": "primary", "label": "Prompt principal (3 ações compartilham)",
        "default_ref": "app.agents.marketing.marketing_agent.MARKETING_SYSTEM",
    }],
    "visual_law_agent": [{
        "slot": "primary", "label": "Prompt principal (3 ações compartilham)",
        "default_ref": "app.agents.visual_law.visual_law_agent.VISUAL_SYSTEM",
    }],
    "coding_agent": [{
        "slot": "primary", "label": "Prompt principal",
        "default_ref": "app.agents.coding.coding_agent.CODING_SYSTEM",
    }],
    "innovation_agent": [{
        "slot": "primary", "label": "Prompt principal",
        "default_ref": "app.agents.innovation.innovation_agent.INNOVATION_SYSTEM",
    }],
    # Slot único "primary", literal inline hoisted pra constante de módulo
    "compliance_agent": [{
        "slot": "primary", "label": "Prompt principal (verificação OAB)",
        "default_ref": "app.agents.compliance.compliance_agent.COMPLIANCE_SYSTEM",
    }],
    "process_agent": [{
        "slot": "primary", "label": "Prompt principal (resumo de andamento)",
        "default_ref": "app.agents.process.process_agent.PROCESS_SUMMARY_SYSTEM",
    }],
    # Caso especial: só 1 dos 3 call sites tem prompt próprio do agente
    "crm_agent": [{
        "slot": "draft_followup",
        "label": "Follow-up de cliente (único prompt específico do CRM — os outros 2 usam o prompt jurídico base, fora de escopo)",
        "default_ref": "app.agents.crm.crm_agent.CRM_FOLLOWUP_SYSTEM",
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


def resolve_default_prompt(default_ref: str) -> str | None:
    """Resolve o texto padrão de um slot a partir do caminho pontilhado até
    sua constante Python. Mesmo padrão de `_resolve_agent_class`
    (app/agents/brain/orchestrator.py) — importlib + getattr — mas
    resolvendo uma constante em vez de uma classe. Fail-soft: caminho
    inválido/módulo quebrado devolve None em vez de derrubar o endpoint."""
    import importlib

    try:
        module_path, const_name = default_ref.rsplit(".", 1)
        module = importlib.import_module(module_path)
        value = getattr(module, const_name)
        return value if isinstance(value, str) else None
    except (ImportError, AttributeError, ValueError):
        return None
