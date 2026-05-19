"""innovation_agent — Detecta gargalos e propõe melhorias ao sistema AFJ."""
from typing import ClassVar
from datetime import datetime, timezone
from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
from app.integrations.anthropic_client import call_claude
import structlog

log = structlog.get_logger()

INNOVATION_SYSTEM = """Você é especialista em inovação para escritórios de advocacia e sistemas jurídicos com IA.
Analise dados de uso, identifique gargalos e proponha melhorias concretas, priorizadas e viáveis.
Toda proposta deve ter: descrição, impacto estimado, esforço de implementação e prioridade."""


class InnovationAgent(BaseAgent):
    name: ClassVar[str] = "innovation_agent"
    description: ClassVar[str] = "Detecta gargalos no sistema e propõe melhorias estratégicas"
    requires_human_approval: ClassVar[bool] = False

    async def execute(self, ctx: AgentContext) -> AgentResult:
        task = ctx.task_input
        foco = task.get("foco", "geral")  # geral, agentes, ux, integrações, processos

        metricas = await self._coletar_metricas(ctx)
        proposta = await self._gerar_proposta(ctx, foco, metricas)

        await self.remember(
            ctx,
            key=f"proposta_inovacao_{datetime.now(timezone.utc).date()}",
            value={"foco": foco, "proposta_resumo": proposta[:300]},
            memory_type="SEMANTIC",
        )

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={
                "foco": foco,
                "proposta": proposta,
                "metricas_base": metricas,
                "gerado_em": datetime.now(timezone.utc).isoformat(),
                "aviso": "Proposta gerada automaticamente. Avalie antes de implementar.",
            },
        )

    async def _coletar_metricas(self, ctx: AgentContext) -> dict:
        if not self.db:
            return {}
        try:
            from sqlalchemy import select, func
            from app.models.agent_run import AgentRun
            result = await self.db.execute(
                select(
                    AgentRun.agent_name,
                    AgentRun.status,
                    func.count().label("total"),
                    func.avg(AgentRun.duration_ms).label("avg_duration"),
                ).group_by(AgentRun.agent_name, AgentRun.status)
            )
            rows = result.all()
            return {f"{r.agent_name}_{r.status}": {"total": r.total, "avg_ms": float(r.avg_duration or 0)} for r in rows}
        except Exception:
            return {}

    async def _gerar_proposta(self, ctx: AgentContext, foco: str, metricas: dict) -> str:
        metricas_str = "\n".join([f"  {k}: {v}" for k, v in list(metricas.items())[:15]]) or "Sem dados ainda"

        prompt = f"""Analise o AFJ CORE SYSTEM e proponha melhorias com foco em: {foco}

MÉTRICAS ATUAIS:
{metricas_str}

Baseado no estado atual do sistema (19 agentes, LangGraph, RAG, HITL), proponha:
1. Top 3 melhorias de alto impacto
2. Identificação de possíveis gargalos
3. Novas funcionalidades recomendadas
4. Melhorias de UX/UI
5. Integrações adicionais recomendadas

Priorize por: impacto no escritório × facilidade de implementação."""

        content, _, _, _ = await call_claude(
            messages=[{"role": "user", "content": prompt}],
            system=INNOVATION_SYSTEM,
            max_tokens=2000,
        )
        return content

    async def _register_tools(self):
        return []
