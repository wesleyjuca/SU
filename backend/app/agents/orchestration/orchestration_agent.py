"""OrchestrationAgent — ponto de entrada standalone para o orquestrador LangGraph.

Recebe um AgentContext com task_type + task_input e delega ao brain/orchestrator.
Usado tanto pela API (/agents/trigger) quanto pelo Celery worker (agent_tasks).
"""
from __future__ import annotations

from typing import ClassVar
import structlog

from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
from app.agents.brain.orchestrator import orchestrator_graph

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
            final_state = await orchestrator_graph.ainvoke(state, config=config)
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
