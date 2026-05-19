"""court_monitor_agent — Monitoramento de pautas de julgamento e publicações DJe."""
from typing import ClassVar
from datetime import datetime, timezone
from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
import structlog

log = structlog.get_logger()


class CourtMonitorAgent(BaseAgent):
    name: ClassVar[str] = "court_monitor_agent"
    description: ClassVar[str] = "Monitora pautas de julgamento, citações no DJe e publicações oficiais"
    requires_human_approval: ClassVar[bool] = False

    async def execute(self, ctx: AgentContext) -> AgentResult:
        task = ctx.task_input
        action = task.get("action", "check_pautas")
        tribunal = task.get("tribunal", "")
        oab = task.get("oab", "")

        if action == "check_pautas":
            return await self._verificar_pautas(ctx, tribunal)
        elif action == "buscar_por_oab":
            return await self._buscar_publicacoes_oab(ctx, oab, tribunal)
        else:
            return AgentResult(
                status=AgentStatus.PARTIAL,
                agent_name=self.name,
                output={"message": f"Ação '{action}' — funcionalidade em implementação progressiva"},
            )

    async def _verificar_pautas(self, ctx: AgentContext, tribunal: str) -> AgentResult:
        """Verifica processos com pauta marcada nos próximos dias."""
        if not self.db:
            return AgentResult(status=AgentStatus.PARTIAL, agent_name=self.name, output={"message": "DB necessário"})

        from sqlalchemy import select
        from app.models.process import LegalProcess, ProcessDeadline
        from datetime import date, timedelta

        hoje = date.today()
        em_7_dias = hoje + timedelta(days=7)

        result = await self.db.execute(
            select(ProcessDeadline)
            .where(
                ProcessDeadline.data_prazo >= hoje,
                ProcessDeadline.data_prazo <= em_7_dias,
                ProcessDeadline.status == "PENDENTE",
            )
            .order_by(ProcessDeadline.data_prazo)
        )
        deadlines = result.scalars().all()

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={
                "prazos_proximos_7_dias": len(deadlines),
                "prazos": [
                    {
                        "id": str(d.id),
                        "descricao": d.descricao,
                        "data": d.data_prazo.isoformat(),
                        "tipo": d.tipo,
                        "process_id": str(d.process_id),
                    }
                    for d in deadlines
                ],
                "verificado_em": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def _buscar_publicacoes_oab(self, ctx: AgentContext, oab: str, tribunal: str) -> AgentResult:
        """Busca publicações nos DJes para um número de OAB."""
        if not oab:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error="OAB obrigatória")

        # Placeholder — integração real com DJe implementada por publicação_monitor_agent
        return AgentResult(
            status=AgentStatus.PARTIAL,
            agent_name=self.name,
            output={
                "oab": oab,
                "tribunal": tribunal,
                "message": f"Busca por OAB {oab} em {tribunal or 'todos os tribunais'} — "
                           "configure o publication_monitor_agent para scan automático do DJe",
                "proximos_passos": "Adicionar credenciais do tribunal nas configurações de integração",
            },
        )

    async def _register_tools(self):
        return []
