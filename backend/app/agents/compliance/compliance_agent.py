"""compliance_agent — Verificações de conformidade LGPD e regulatória."""
from typing import ClassVar
from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
from app.integrations.anthropic_client import call_claude
import structlog

log = structlog.get_logger()


class ComplianceAgent(BaseAgent):
    name: ClassVar[str] = "compliance_agent"
    description: ClassVar[str] = "Verificações LGPD, conformidade OAB e compliance regulatório"
    requires_human_approval: ClassVar[bool] = False

    async def execute(self, ctx: AgentContext) -> AgentResult:
        task = ctx.task_input
        action = task.get("action", "lgpd_check")

        if action == "lgpd_check":
            return await self._verificar_lgpd(ctx, task)
        elif action == "oab_compliance":
            return await self._verificar_oab(ctx, task)
        else:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error=f"Ação: {action}")

    async def _verificar_lgpd(self, ctx: AgentContext, task: dict) -> AgentResult:
        if not self.db:
            return AgentResult(status=AgentStatus.SUCCESS, agent_name=self.name, output={"message": "DB necessário"})

        from sqlalchemy import select, func
        from app.models.client import Client

        sem_lgpd = await self.db.execute(
            select(func.count()).where(Client.lgpd_consent == False, Client.status == "ATIVO")
        )
        count_sem_lgpd = sem_lgpd.scalar()

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={
                "clientes_sem_consentimento_lgpd": count_sem_lgpd,
                "status": "ATENCAO" if count_sem_lgpd > 0 else "OK",
                "recomendacao": f"Coletar consentimento LGPD de {count_sem_lgpd} cliente(s) ativo(s)" if count_sem_lgpd > 0 else "Conformidade LGPD OK",
            },
        )

    async def _verificar_oab(self, ctx: AgentContext, task: dict) -> AgentResult:
        documento = task.get("documento", "")
        if not documento:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error="documento obrigatório")

        content, input_t, output_t, cost = await call_claude(
            messages=[{"role": "user", "content": f"Verifique se este documento de marketing jurídico está em conformidade com o Código de Ética da OAB:\n\n{documento[:2000]}\n\nIdentifique: violações (se houver), sugestões de adequação."}],
            system="Você é especialista em ética da OAB e marketing jurídico conforme CFOAB.",
            max_tokens=800,
        )
        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={"analise_oab": content},
            tokens_used=input_t + output_t,
            cost_usd=cost,
        )

    async def _register_tools(self):
        return []
