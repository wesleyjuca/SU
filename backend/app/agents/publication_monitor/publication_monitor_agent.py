"""publication_monitor_agent — Scan diário de Diários Oficiais e DJes."""
from typing import ClassVar
from datetime import datetime, timezone
from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
import structlog

log = structlog.get_logger()


class PublicationMonitorAgent(BaseAgent):
    name: ClassVar[str] = "publication_monitor_agent"
    description: ClassVar[str] = "Scan diário de DJes e Diários Oficiais para OABs cadastradas"
    requires_human_approval: ClassVar[bool] = False

    async def execute(self, ctx: AgentContext) -> AgentResult:
        task = ctx.task_input
        oabs = task.get("oabs", [])  # lista de OABs para monitorar
        data_edicao = task.get("data", datetime.now(timezone.utc).date().isoformat())

        if not oabs and self.db:
            oabs = await self._obter_oabs_cadastradas()

        if not oabs:
            return AgentResult(
                status=AgentStatus.PARTIAL,
                agent_name=self.name,
                output={"message": "Nenhuma OAB cadastrada para monitoramento. Adicione advogados com OAB no sistema."},
            )

        resultados = []
        for oab in oabs:
            matches = await self._scan_dje(oab, data_edicao)
            if matches:
                resultados.extend(matches)

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={
                "data_edicao": data_edicao,
                "oabs_monitoradas": len(oabs),
                "publicacoes_encontradas": len(resultados),
                "resultados": resultados,
                "proxima_execucao": "Agendada via Celery Beat diariamente às 07h",
            },
        )

    async def _obter_oabs_cadastradas(self) -> list[str]:
        from sqlalchemy import select
        from app.models.user import User
        result = await self.db.execute(
            select(User.oab_number).where(User.oab_number.isnot(None), User.is_active == True)
        )
        return [r[0] for r in result.all() if r[0]]

    async def _scan_dje(self, oab: str, data: str) -> list[dict]:
        """
        Scan do DJe para uma OAB específica.
        Implementação real: download PDF do DJe + OCR + busca textual.
        Por ora retorna placeholder — implemente por tribunal.
        """
        log.info("publication_scan", oab=oab, data=data, status="placeholder")
        return []  # expansão: integrar com APIs oficiais dos TJs

    async def _register_tools(self):
        return []
