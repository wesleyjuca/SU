"""publication_monitor_agent — Scan de Diários Oficiais/DJe sob demanda, via
services.dje_monitor.scan_publicacoes (mesma varredura real usada pelo job
diário do Celery Beat)."""
from typing import ClassVar
from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
import structlog

log = structlog.get_logger()


class PublicationMonitorAgent(BaseAgent):
    name: ClassVar[str] = "publication_monitor_agent"
    description: ClassVar[str] = "Varredura sob demanda de DJes/Diários Oficiais para as OABs do escritório"
    requires_human_approval: ClassVar[bool] = False

    async def execute(self, ctx: AgentContext) -> AgentResult:
        if not self.db:
            return AgentResult(
                status=AgentStatus.PARTIAL,
                agent_name=self.name,
                output={"message": "DB necessário para varredura de DJe."},
            )

        task = ctx.task_input
        dias_retro = int(task.get("dias_retro", 1) or 1)

        from app.services.dje_monitor import scan_publicacoes

        try:
            resumo = await scan_publicacoes(self.db, tenant_id=ctx.tenant_id, dias_retro=dias_retro)
        except Exception as exc:
            log.warning("dje_scan_manual_failed", tenant=str(ctx.tenant_id), error=str(exc))
            return AgentResult(
                status=AgentStatus.PARTIAL,
                agent_name=self.name,
                output={"message": f"Varredura parcial — falha na consulta à Comunica: {exc}"},
            )

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={
                "oabs_monitoradas": resumo.get("oabs_monitoradas", 0),
                "publicacoes_encontradas": resumo.get("intimacoes_novas", 0),
                "intimacoes_criadas": resumo.get("intimacoes_novas", 0),
                "processos_casados": resumo.get("casadas_com_processo", 0),
                "disparo": "manual (on-demand via /agents/trigger) — complementar ao job diário do Celery Beat (07h30)",
            },
        )

    async def _register_tools(self):
        return []
