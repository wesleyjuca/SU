"""analytics_agent — Métricas do escritório, taxa de êxito e produtividade."""
from typing import ClassVar
from datetime import datetime, timezone
from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
import structlog

log = structlog.get_logger()


class AnalyticsAgent(BaseAgent):
    name: ClassVar[str] = "analytics_agent"
    description: ClassVar[str] = "Métricas de desempenho, taxa de êxito e relatórios executivos"
    requires_human_approval: ClassVar[bool] = False

    async def execute(self, ctx: AgentContext) -> AgentResult:
        if not self.db:
            return AgentResult(
                status=AgentStatus.SUCCESS,
                agent_name=self.name,
                output={"message": "Analytics operacional — conecte o DB para dados reais."},
            )

        from sqlalchemy import select, func
        from app.models.process import LegalProcess
        from app.models.agent_run import AgentRun
        from app.models.agent_run import Approval

        # Processos por situação
        proc_result = await self.db.execute(
            select(LegalProcess.situacao, func.count().label("total")).group_by(LegalProcess.situacao)
        )
        processos_por_situacao = {r.situacao: r.total for r in proc_result.all()}

        # Processos por área
        area_result = await self.db.execute(
            select(LegalProcess.area_direito, func.count().label("total"))
            .where(LegalProcess.area_direito.isnot(None))
            .group_by(LegalProcess.area_direito)
        )
        processos_por_area = {r.area_direito: r.total for r in area_result.all()}

        # Custo total de IA
        custo_result = await self.db.execute(
            select(
                func.sum(AgentRun.cost_usd).label("custo_total"),
                func.sum(AgentRun.tokens_used).label("tokens_total"),
                func.count().label("execucoes"),
            )
        )
        custo_row = custo_result.one()

        # Taxa de aprovação HITL
        approval_result = await self.db.execute(
            select(Approval.status, func.count().label("total")).group_by(Approval.status)
        )
        approvals = {r.status: r.total for r in approval_result.all()}
        total_approvals = sum(approvals.values()) or 1
        taxa_aprovacao = round(approvals.get("APROVADO", 0) / total_approvals * 100, 1)

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={
                "processos": {
                    "por_situacao": processos_por_situacao,
                    "por_area": processos_por_area,
                    "total": sum(processos_por_situacao.values()),
                },
                "ia": {
                    "custo_total_usd": float(custo_row.custo_total or 0),
                    "tokens_total": int(custo_row.tokens_total or 0),
                    "execucoes": int(custo_row.execucoes or 0),
                    "taxa_aprovacao_hitl": taxa_aprovacao,
                },
                "gerado_em": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def _register_tools(self):
        return []
