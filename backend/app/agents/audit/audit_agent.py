"""audit_agent — Revisão de logs, conformidade e relatórios de auditoria."""
from typing import ClassVar
from datetime import datetime, timezone, timedelta
from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
import structlog

log = structlog.get_logger()


class AuditAgent(BaseAgent):
    name: ClassVar[str] = "audit_agent"
    description: ClassVar[str] = "Revisão de logs de auditoria e detecção de anomalias"
    requires_human_approval: ClassVar[bool] = False

    async def execute(self, ctx: AgentContext) -> AgentResult:
        if not self.db:
            return AgentResult(status=AgentStatus.SUCCESS, agent_name=self.name, output={"message": "DB não disponível"})

        from sqlalchemy import select, func
        from app.models.audit_log import AuditLog

        periodo_horas = ctx.task_input.get("periodo_horas", 24)
        desde = datetime.now(timezone.utc) - timedelta(hours=periodo_horas)

        result = await self.db.execute(
            select(
                AuditLog.action,
                AuditLog.success,
                func.count().label("total"),
            )
            .where(AuditLog.timestamp >= desde)
            .group_by(AuditLog.action, AuditLog.success)
        )
        rows = result.all()

        falhas = [r for r in rows if not r.success]
        total_eventos = sum(r.total for r in rows)
        total_falhas = sum(r.total for r in falhas)

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={
                "periodo_horas": periodo_horas,
                "total_eventos": total_eventos,
                "total_falhas": total_falhas,
                "taxa_falha_pct": round(total_falhas / max(total_eventos, 1) * 100, 2),
                "acoes_com_falha": [{"action": r.action, "total": r.total} for r in falhas],
                "gerado_em": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def _register_tools(self):
        return []
