"""OrchestrationAgent — adaptador entre um `AgentContext` e o grafo LangGraph.

Recebe um `AgentContext` com `task_type` + `task_input`, invoca
`brain/orchestrator` e traduz o state final em `AgentResult`.

QUEM DE FATO USA (corrigido: a versão anterior deste docstring afirmava que a
API e o worker passavam por aqui, o que o código contradiz):
- `POST /agents/trigger` (`api/v1/agents.py:295`) e o worker Celery
  (`workers/tasks/agent_tasks.py:139-141`) **não** instanciam esta classe —
  os dois montam o state à mão e chamam `get_orchestrator_graph().ainvoke()`
  direto.
- Esta classe é alcançada DENTRO do grafo, via
  `resolve_agent_class("orchestration_agent")`, que é a rota de fallback de
  `get_chain()` para `task_type` não mapeado (`brain/router.py:93-94`).

Consequência conhecida dessa rota de fallback, sem guard no código: ela aponta
para esta própria classe, então um `task_type` desconhecido produz
`execute` → grafo → `execute_chain_step` → `run` → grafo, com o mesmo
`thread_id`. As precondições estão fixadas em
`tests/test_unit/test_orchestration_agent.py`; o comportamento em runtime não
foi confirmado.
"""
from __future__ import annotations

from typing import ClassVar
import structlog

from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
from app.agents.brain.orchestrator import get_orchestrator_graph

log = structlog.get_logger()


class OrchestrationAgent(BaseAgent):
    name: ClassVar[str] = "orchestration_agent"
    description: ClassVar[str] = (
        "Ponto de entrada do sistema multiagente. Classifica o intent, "
        "recupera memória contextual e despacha para o agente especializado correto."
    )
    version: ClassVar[str] = "1.0.0"
    requires_human_approval: ClassVar[bool] = False

    async def execute(self, ctx: AgentContext) -> AgentResult:
        log.info(
            "orchestration_start",
            task_type=ctx.task_type,
            run_id=str(ctx.run_id),
            priority=ctx.priority,
        )

        state = {
            "context": ctx,
            "route": "",
            "agent_results": [],
            "pending_approval": None,
            "final_output": None,
            "error": None,
            "done": False,
        }
        config = {"configurable": {"thread_id": str(ctx.run_id)}}

        try:
            final_state = await get_orchestrator_graph().ainvoke(state, config=config)
        except Exception as exc:
            log.error("orchestration_failed", run_id=str(ctx.run_id), error=str(exc))
            return AgentResult(
                status=AgentStatus.FAILED,
                agent_name=self.name,
                output={"error": str(exc)},
                error=str(exc),
            )

        # Determinar status final a partir do estado
        if final_state.get("error"):
            return AgentResult(
                status=AgentStatus.FAILED,
                agent_name=self.name,
                output={"error": final_state["error"]},
                error=final_state["error"],
            )

        if final_state.get("pending_approval"):
            return AgentResult(
                status=AgentStatus.AWAITING_APPROVAL,
                agent_name=self.name,
                output=final_state.get("final_output") or {},
                approval_required=final_state["pending_approval"],
            )

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output=final_state.get("final_output") or {},
        )

    def _register_tools(self):
        return []
