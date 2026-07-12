"""
AFJ_CORE_BRAIN — Orquestrador Central com LangGraph.

Fluxo:
  classify_intent → retrieve_memory → execute_agent → check_approval
  → [INTERRUPT para aprovação humana, se necessário]
  → post_process → audit_close
"""
from typing import TypedDict
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
import structlog

from app.agents.brain.context import AgentContext
from app.agents.brain.router import classify_task
from app.agents.base.result import AgentResult, AgentStatus

log = structlog.get_logger()


class OrchestratorState(TypedDict):
    context: AgentContext
    route: str
    agent_results: list[AgentResult]
    pending_approval: dict | None
    final_output: dict | None
    error: str | None
    done: bool


async def node_classify_intent(state: OrchestratorState) -> OrchestratorState:
    ctx = state["context"]
    route = classify_task(ctx.task_type, ctx.task_input)
    log.info("orchestrator_route", task=ctx.task_type, route=route)
    return {**state, "route": route}


async def node_retrieve_memory(state: OrchestratorState) -> OrchestratorState:
    ctx = state["context"]
    # Memory retrieval é responsabilidade do agente individual via recall()
    # Este nó prepara metadados de contexto para o agente
    ctx.set_state("memory_retrieved", True)
    return state


async def node_execute_agent(state: OrchestratorState) -> OrchestratorState:
    ctx = state["context"]
    route = state["route"]

    agent_class = _resolve_agent_class(route)
    if not agent_class:
        return {**state, "error": f"Agente não encontrado: {route}", "done": True}

    # Injeta dependências reais: sem isto o RAG (recall) retorna [] e nada é
    # persistido (Document/Petition/AgentMemory ficam órfãos).
    from app.db.base import AsyncSessionLocal
    from app.db.redis import get_redis

    redis = await get_redis()
    qdrant = await _get_qdrant_if_configured()

    from app.integrations.byok import user_ai_creds

    async with AsyncSessionLocal() as session:
        # BYOK: se o usuário disparador tem IA própria ativa, usa a chave dele
        # (economiza tokens do sistema). O contextvar propaga até o call_llm.
        agent = agent_class(db=session, redis=redis, qdrant=qdrant)
        async with user_ai_creds(session, ctx.triggered_by, ctx.task_type):
            result = await agent.run(ctx)
        try:
            if result.status == AgentStatus.FAILED:
                await session.rollback()
            else:
                await session.commit()
        except Exception as exc:
            await session.rollback()
            log.error("agent_session_commit_failed", route=route, error=str(exc))

    results = state.get("agent_results", []) + [result]

    if result.status == AgentStatus.FAILED:
        return {**state, "agent_results": results, "error": result.error, "done": True}

    return {**state, "agent_results": results}


async def node_check_approval(state: OrchestratorState) -> OrchestratorState:
    results = state.get("agent_results", [])
    last_result = results[-1] if results else None

    if last_result and last_result.needs_approval:
        return {
            **state,
            "pending_approval": last_result.approval_required,
        }
    return state


def route_after_approval_check(state: OrchestratorState) -> str:
    if state.get("pending_approval"):
        return "awaiting_approval"
    return "post_process"


async def node_awaiting_approval(state: OrchestratorState) -> OrchestratorState:
    """
    Nó de interrupt — suspende o workflow aqui.
    O workflow é retomado pela API de aprovações quando o humano decide.
    O estado é serializado no Redis via LangGraph checkpoint.
    """
    log.info("orchestrator_awaiting_approval", run_id=str(state["context"].run_id))
    # LangGraph interrupt() mantém o estado aqui até retomada
    return state


async def node_post_process(state: OrchestratorState) -> OrchestratorState:
    ctx = state["context"]
    results = state.get("agent_results", [])

    final_output = {
        "run_id": str(ctx.run_id),
        "task_type": ctx.task_type,
        "agents_invoked": ctx.agents_invoked,
        "total_tokens": ctx.total_tokens,
        "total_cost_usd": ctx.total_cost_usd,
        "results": [r.to_dict() for r in results],
    }
    return {**state, "final_output": final_output, "done": True}


async def node_audit_close(state: OrchestratorState) -> OrchestratorState:
    ctx = state["context"]
    log.info(
        "orchestrator_done",
        run_id=str(ctx.run_id),
        agents=ctx.agents_invoked,
        tokens=ctx.total_tokens,
        cost=ctx.total_cost_usd,
    )
    return state


def build_orchestrator_graph() -> StateGraph:
    graph = StateGraph(OrchestratorState)

    graph.add_node("classify_intent", node_classify_intent)
    graph.add_node("retrieve_memory", node_retrieve_memory)
    graph.add_node("execute_agent", node_execute_agent)
    graph.add_node("check_approval", node_check_approval)
    graph.add_node("awaiting_approval", node_awaiting_approval)
    graph.add_node("post_process", node_post_process)
    graph.add_node("audit_close", node_audit_close)

    graph.set_entry_point("classify_intent")
    graph.add_edge("classify_intent", "retrieve_memory")
    graph.add_edge("retrieve_memory", "execute_agent")
    graph.add_edge("execute_agent", "check_approval")
    graph.add_conditional_edges(
        "check_approval",
        route_after_approval_check,
        {"awaiting_approval": "awaiting_approval", "post_process": "post_process"},
    )
    graph.add_edge("awaiting_approval", END)   # suspend — retomado pela API
    graph.add_edge("post_process", "audit_close")
    graph.add_edge("audit_close", END)

    return graph


async def _get_qdrant_if_configured():
    """Retorna o cliente Qdrant apenas se configurado — senão None (RAG desligado).

    Mesmo guard do warmup em app/core/events.py: evita tentar conectar a um
    placeholder (ambiente de preview sem Qdrant) e travar o nó do agente.
    """
    from app.config import settings as _cfg
    configured = bool(
        _cfg.QDRANT_API_KEY or
        (_cfg.QDRANT_URL and _cfg.QDRANT_URL not in {"http://qdrant:6333", "http://localhost:6333"})
    )
    if not configured:
        return None
    try:
        from app.db.qdrant import get_qdrant
        return await get_qdrant()
    except Exception as exc:
        log.warning("qdrant_unavailable_for_agent", error=str(exc))
        return None


def _resolve_agent_class(route: str):
    """Resolve a classe do agente pela rota (sem instanciar)."""
    agent_map = {
        # Rota-padrão de tarefas ambíguas (classify_task cai aqui) — precisa
        # resolver, senão qualquer tarefa não mapeada quebra ("Agente não encontrado").
        "orchestration_agent": "app.agents.orchestration.orchestration_agent.OrchestrationAgent",
        "process_agent": "app.agents.process.process_agent.ProcessAgent",
        "petition_agent": "app.agents.petition.petition_agent.PetitionAgent",
        "review_agent": "app.agents.review.review_agent.ReviewAgent",
        "jurisprudence_agent": "app.agents.jurisprudence.jurisprudence_agent.JurisprudenceAgent",
        "strategy_agent": "app.agents.strategy.strategy_agent.StrategyAgent",
        "court_monitor_agent": "app.agents.court_monitor.court_monitor_agent.CourtMonitorAgent",
        "crm_agent": "app.agents.crm.crm_agent.CRMAgent",
        "contract_agent": "app.agents.contract.contract_agent.ContractAgent",
        "financial_agent": "app.agents.financial.financial_agent.FinancialAgent",
        "marketing_agent": "app.agents.marketing.marketing_agent.MarketingAgent",
        "analytics_agent": "app.agents.analytics.analytics_agent.AnalyticsAgent",
        "ocr_agent": "app.agents.ocr.ocr_agent.OCRAgent",
        "audit_agent": "app.agents.audit.audit_agent.AuditAgent",
        "compliance_agent": "app.agents.compliance.compliance_agent.ComplianceAgent",
        "visual_law_agent": "app.agents.visual_law.visual_law_agent.VisualLawAgent",
        "coding_agent": "app.agents.coding.coding_agent.CodingAgent",
        "innovation_agent": "app.agents.innovation.innovation_agent.InnovationAgent",
        "publication_monitor_agent": "app.agents.publication_monitor.publication_monitor_agent.PublicationMonitorAgent",
    }

    class_path = agent_map.get(route)
    if not class_path:
        return None

    module_path, class_name = class_path.rsplit(".", 1)
    try:
        import importlib
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    except (ImportError, AttributeError) as exc:
        log.error("agent_import_failed", route=route, error=str(exc))
        return None


# Lazy singleton — built on first call so a LangGraph failure doesn't crash the whole app
_orchestrator_graph = None


def get_orchestrator_graph():
    global _orchestrator_graph
    if _orchestrator_graph is None:
        checkpointer = MemorySaver()
        _orchestrator_graph = build_orchestrator_graph().compile(checkpointer=checkpointer)
    return _orchestrator_graph
