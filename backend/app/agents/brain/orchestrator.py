"""
AFJ_CORE_BRAIN — Orquestrador Central com LangGraph.

Fluxo:
  classify_intent → retrieve_memory → execute_agent ⟲ (loop pelos passos da
  chain enquanto houver próximo passo e o passo atual tiver sucedido) →
  check_approval → [INTERRUPT para aprovação humana, se necessário]
  → post_process → audit_close

`route`/`chain`/`chain_index` (Fase 169.1): `chain` é a lista completa de
agentes da tarefa (1 elemento pra rotas diretas, N pra uma chain declarada em
`TASK_ROUTE_MAP`); `chain_index` é o passo corrente; `route` é sempre
`chain[chain_index]`. `execute_agent` avança `chain_index`/`route` e volta
pra si mesmo (via `route_after_execute_agent`) enquanto o passo anterior
tiver sido SUCCESS e restar passo — uma chain com gate HITL no meio/fim para
naturalmente em `check_approval` como uma rota única pararia, sem pular pro
próximo passo (retomada automática pós-aprovação é a Fase 169.2).

Chamador padrão: `agents/orchestration/orchestration_agent.py` (API
`/agents/trigger`, worker Celery) — monta o `AgentContext` e delega a
execução real do grafo pra cá. Este módulo é o motor; aquele é só o adaptador
de entrada.
"""
from typing import TypedDict
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
import structlog

from app.agents.brain.context import AgentContext
from app.agents.brain.router import get_chain
from app.agents.brain.chain_projectors import project_output
from app.agents.base.result import AgentResult, AgentStatus

log = structlog.get_logger()


class OrchestratorState(TypedDict):
    context: AgentContext
    route: str
    chain: list[str]
    chain_index: int
    agent_results: list[AgentResult]
    pending_approval: dict | None
    final_output: dict | None
    error: str | None
    done: bool


async def node_classify_intent(state: OrchestratorState) -> OrchestratorState:
    ctx = state["context"]
    chain = get_chain(ctx.task_type, ctx.task_input)
    log.info("orchestrator_route", task=ctx.task_type, chain=chain)
    return {**state, "chain": chain, "chain_index": 0, "route": chain[0]}


async def node_retrieve_memory(state: OrchestratorState) -> OrchestratorState:
    ctx = state["context"]
    # Memory retrieval é responsabilidade do agente individual via recall()
    # Este nó prepara metadados de contexto para o agente
    ctx.set_state("memory_retrieved", True)
    return state


async def execute_chain_step(ctx: AgentContext, chain: list[str], chain_index: int) -> AgentResult:
    """Executa 1 passo de uma chain: resolve o agente, roda com sessão/redis/
    qdrant/BYOK próprios, persiste o `AgentStep` correspondente.

    Extraído do loop do orquestrador (Fase 169.2) porque a retomada pós-
    aprovação (`app/services/chain_resume.py`) precisa exatamente desta
    mesma unidade de trabalho fora do grafo LangGraph — mesmo passo, 2
    chamadores (o loop `node_execute_agent` abaixo, e a retomada)."""
    route = chain[chain_index]

    agent_class = resolve_agent_class(route)
    if not agent_class:
        return AgentResult(status=AgentStatus.FAILED, agent_name=route, error=f"Agente não encontrado: {route}")

    # Injeta dependências reais: sem isto o RAG (recall) retorna [] e nada é
    # persistido (Document/Petition/AgentMemory ficam órfãos).
    from app.db.base import AsyncSessionLocal
    from app.db.redis import get_redis

    redis = await get_redis()
    qdrant = await _get_qdrant_if_configured()

    from app.integrations.byok import user_ai_creds

    step_input_snapshot = dict(ctx.task_input)

    async with AsyncSessionLocal() as session:
        # BYOK: se o usuário disparador tem IA própria ativa, usa a chave dele
        # (economiza tokens do sistema). O contextvar propaga até o call_llm.
        agent = agent_class(db=session, redis=redis, qdrant=qdrant)
        # Fase 196 — streaming de resposta via WebSocket só pra disparo
        # direto (chain de 1 passo só): uma chain multi-agente já usa o
        # texto de um passo como entrada do próximo (project_output) antes
        # do usuário ver qualquer coisa, então não há "resposta ao vivo"
        # útil pra streamar no meio do caminho.
        ctx.stream_enabled = len(chain) == 1
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

        # Fase 169.1 — ativa o modelo AgentStep (existia, nunca era gravado):
        # 1 linha por passo executado, chain ou rota única, pra dar
        # visibilidade real de progresso a uma execução multi-agente.
        try:
            from app.models.agent_run import AgentStep
            # `_status` embutido no output_json (não é um campo real do
            # output do agente) — AgentStep não tem coluna de status própria;
            # em vez de migrar o schema só pra isso, a API (agents.py) extrai
            # essa chave ao montar AgentStepResponse.
            session.add(AgentStep(
                run_id=ctx.run_id,
                step_number=chain_index,
                step_name=route,
                input_json=step_input_snapshot,
                output_json={"_status": result.status.value, **(result.output or {})},
                duration_ms=result.duration_ms,
            ))
            await session.commit()
        except Exception as exc:
            await session.rollback()
            log.error("agent_step_persist_failed", route=route, error=str(exc))

    return result


async def node_execute_agent(state: OrchestratorState) -> OrchestratorState:
    ctx = state["context"]
    route = state["route"]
    chain = state.get("chain") or [route]
    chain_index = state.get("chain_index", 0)

    result = await execute_chain_step(ctx, chain, chain_index)

    results = state.get("agent_results", []) + [result]

    if result.status == AgentStatus.FAILED:
        return {**state, "agent_results": results, "chain_index": chain_index, "error": result.error, "done": True}

    next_index = chain_index + 1
    if result.status == AgentStatus.SUCCESS and next_index < len(chain):
        next_route = chain[next_index]
        ctx.task_input = project_output(route, next_route, result, ctx)
        return {**state, "agent_results": results, "chain_index": next_index, "route": next_route}

    return {**state, "agent_results": results, "chain_index": chain_index}


def route_after_execute_agent(state: OrchestratorState) -> str:
    """Fase 169.1 — decide se ainda há passo pendente na chain.

    Só continua o loop quando o último passo teve SUCCESS: FAILED já marca
    `done=True` (o grafo do LangGraph segue os edges mesmo assim, mas o nó
    seguinte vê `error` setado); AWAITING_APPROVAL precisa parar em
    `check_approval` pra criar a Approval antes de decidir o que fazer —
    nunca pula pro próximo passo sem gate humano resolvido.
    """
    chain = state.get("chain") or []
    results = state.get("agent_results", [])
    last_result = results[-1] if results else None

    # `results` acumula 1 entrada por passo já executado — enquanto for menor
    # que o tamanho da chain, ainda há passo pendente (`chain_index`, nesse
    # ponto, já foi avançado por node_execute_agent para APONTAR pro próximo
    # passo, então comparar contra `len(results)` em vez de `chain_index` é o
    # que evita pular o último passo por off-by-one).
    if last_result and last_result.status == AgentStatus.SUCCESS and len(results) < len(chain):
        return "execute_agent"
    return "check_approval"


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

    O grafo TERMINA (edge `awaiting_approval → END`), não fica pausado em
    memória: a `Approval` já foi criada por `node_check_approval` e a
    resolução humana (`app/api/v1/approvals.py::resolve_approval`) age
    diretamente sobre o registro correspondente (Document/Petition/Contract),
    de forma síncrona — não existe retomada deste grafo LangGraph via
    checkpoint (o `MemorySaver` configurado em `get_orchestrator_graph` não é
    usado para isso; ver docstring de `app/services/approval.py`). Numa chain
    com gate no meio, os passos restantes NÃO são executados automaticamente
    após a aprovação — isso é a Fase 169.2.
    """
    log.info(
        "orchestrator_awaiting_approval",
        run_id=str(state["context"].run_id),
        chain_index=state.get("chain_index", 0),
        chain_len=len(state.get("chain") or []),
    )
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
    # Fase 174.2 — `state["error"]` já era setado por node_execute_agent
    # quando um passo FAILED (ver linha ~141), mas nada lia depois: o run
    # inteiro era gravado como SUCCESS mesmo com a chain interrompida por
    # falha real de um passo. Propagar pro final_output, que é o que
    # _run_async (app/workers/tasks/agent_tasks.py) de fato inspeciona pra
    # decidir o status final.
    error = state.get("error")
    if error:
        final_output["error"] = error
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
    graph.add_conditional_edges(
        "execute_agent",
        route_after_execute_agent,
        {"execute_agent": "execute_agent", "check_approval": "check_approval"},
    )
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


def resolve_agent_class(route: str):
    """Resolve a classe do agente pela rota (sem instanciar).

    Público (Fase 169.2) — usado tanto por `execute_chain_step` (acima)
    quanto por `app/services/chain_resume.py`."""
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
        # Fase 140.2 — executor genérico de agentes customizados aprovados
        # (ADMIN propõe, SUPERADMIN aprova). Não é um agente por proposta;
        # 1 classe só, parametrizada por task_input.custom_agent_id.
        "custom_agent": "app.agents.custom.custom_agent_executor.CustomAgentExecutor",
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
