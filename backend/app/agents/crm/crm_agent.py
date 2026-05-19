"""crm_agent — Gestão de clientes, leads e interações."""
from typing import ClassVar
from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
from app.integrations.anthropic_client import call_claude, AFJ_LEGAL_SYSTEM_PROMPT
import structlog

log = structlog.get_logger()


class CRMAgent(BaseAgent):
    name: ClassVar[str] = "crm_agent"
    description: ClassVar[str] = "Gestão de clientes, leads, follow-up e automação do CRM"
    requires_human_approval: ClassVar[bool] = False

    async def execute(self, ctx: AgentContext) -> AgentResult:
        task = ctx.task_input
        action = task.get("action", "analyze_lead")

        if action == "analyze_lead":
            return await self._analisar_lead(ctx, task)
        elif action == "draft_followup":
            return await self._rascunhar_followup(ctx, task)
        elif action == "classify_client":
            return await self._classificar_cliente(ctx, task)
        else:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error=f"Ação desconhecida: {action}")

    async def _analisar_lead(self, ctx: AgentContext, task: dict) -> AgentResult:
        nome = task.get("nome", "")
        descricao = task.get("descricao_caso", "")
        canal = task.get("canal", "")

        prompt = f"""Analise este lead para o escritório AFJ Advogados:

Nome: {nome}
Canal de origem: {canal}
Descrição do caso: {descricao}

Retorne:
1. Área do direito identificada
2. Urgência estimada (ALTA/MÉDIA/BAIXA)
3. Potencial financeiro estimado (faixas: <5k / 5-20k / 20-50k / >50k)
4. Próximos passos recomendados
5. Perguntas a fazer na triagem"""

        content, input_t, output_t, cost = await call_claude(
            messages=[{"role": "user", "content": prompt}],
            system=AFJ_LEGAL_SYSTEM_PROMPT,
            max_tokens=1000,
        )

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={"analise": content, "lead_nome": nome, "canal": canal},
            tokens_used=input_t + output_t,
            cost_usd=cost,
        )

    async def _rascunhar_followup(self, ctx: AgentContext, task: dict) -> AgentResult:
        cliente = task.get("cliente_nome", "")
        contexto = task.get("contexto", "")
        canal = task.get("canal", "WhatsApp")

        prompt = f"""Redija uma mensagem de follow-up profissional para o cliente {cliente} via {canal}.
Contexto: {contexto}
Tom: profissional, empático, objetivo. Máximo 5 linhas."""

        content, input_t, output_t, cost = await call_claude(
            messages=[{"role": "user", "content": prompt}],
            system="Você é assistente do escritório AFJ Advogados. Escreva com cordialidade e profissionalismo.",
            max_tokens=300,
        )

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={"mensagem_rascunho": content, "canal": canal},
            tokens_used=input_t + output_t,
            cost_usd=cost,
        )

    async def _classificar_cliente(self, ctx: AgentContext, task: dict) -> AgentResult:
        historico = task.get("historico", "")
        content, input_t, output_t, cost = await call_claude(
            messages=[{"role": "user", "content": f"Classifique este cliente AFJ com base no histórico:\n{historico}\n\nRetorne: segmento (PLATINUM/GOLD/SILVER/REGULAR), frequência estimada de demanda, área predominante."}],
            system=AFJ_LEGAL_SYSTEM_PROMPT,
            max_tokens=300,
        )
        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={"classificacao": content},
            tokens_used=input_t + output_t,
            cost_usd=cost,
        )

    async def _register_tools(self):
        return []
