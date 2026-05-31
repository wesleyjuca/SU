"""financial_agent — Gestão financeira, honorários e relatórios."""
from typing import ClassVar
from datetime import datetime, timezone
from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
import structlog

log = structlog.get_logger()


class FinancialAgent(BaseAgent):
    name: ClassVar[str] = "financial_agent"
    description: ClassVar[str] = "Relatórios financeiros, controle de honorários e inadimplência"
    requires_human_approval: ClassVar[bool] = False

    async def execute(self, ctx: AgentContext) -> AgentResult:
        task = ctx.task_input
        action = task.get("action", "summary")

        if action == "summary" and self.db:
            return await self._resumo_financeiro(ctx)
        elif action == "check_overdue" and self.db:
            return await self._verificar_inadimplentes(ctx)
        else:
            return AgentResult(
                status=AgentStatus.SUCCESS,
                agent_name=self.name,
                output={"message": "Módulo financeiro operacional. Configure dados para relatórios."},
            )

    async def _resumo_financeiro(self, ctx: AgentContext) -> AgentResult:
        from sqlalchemy import select, func
        from app.models.financial import FinancialEntry
        from decimal import Decimal

        result = await self.db.execute(
            select(
                FinancialEntry.tipo,
                FinancialEntry.status,
                func.sum(FinancialEntry.valor).label("total"),
                func.count().label("quantidade"),
            ).group_by(FinancialEntry.tipo, FinancialEntry.status)
        )
        rows = result.all()

        receita_total = sum(r.total for r in rows if r.tipo == "RECEITA" and r.status == "PAGO") or Decimal("0")
        receita_pendente = sum(r.total for r in rows if r.tipo == "RECEITA" and r.status == "PENDENTE") or Decimal("0")
        despesa_total = sum(r.total for r in rows if r.tipo == "DESPESA") or Decimal("0")

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={
                "receita_recebida": float(receita_total),
                "receita_pendente": float(receita_pendente),
                "despesas": float(despesa_total),
                "resultado_liquido": float(receita_total - despesa_total),
                "gerado_em": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def _verificar_inadimplentes(self, ctx: AgentContext) -> AgentResult:
        from sqlalchemy import select
        from app.models.financial import FinancialEntry
        from datetime import date

        today = date.today()
        result = await self.db.execute(
            select(FinancialEntry).where(
                FinancialEntry.tipo == "RECEITA",
                FinancialEntry.status == "PENDENTE",
                FinancialEntry.data_vencimento < today,
            ).order_by(FinancialEntry.data_vencimento)
        )
        vencidos = result.scalars().all()

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={
                "inadimplentes": len(vencidos),
                "valor_total_vencido": float(sum(e.valor for e in vencidos)),
                "registros": [
                    {
                        "id": str(e.id),
                        "descricao": e.descricao,
                        "valor": float(e.valor),
                        "vencimento": e.data_vencimento.isoformat() if e.data_vencimento else None,
                    }
                    for e in vencidos[:20]
                ],
            },
        )

    async def _register_tools(self):
        return []
