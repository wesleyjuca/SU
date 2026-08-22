"""
strategy_agent — Análise estratégica jurídica.

Analisa o caso, identifica teses viáveis, avalia riscos e propõe
a melhor linha de atuação baseada em dados reais do processo e jurisprudência.
"""
import time
from typing import ClassVar
from sqlalchemy import select, func
from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
from app.integrations.anthropic_client import call_claude, AFJ_LEGAL_SYSTEM_PROMPT
from app.models.process import LegalProcess
import structlog

log = structlog.get_logger()

STRATEGY_SYSTEM = AFJ_LEGAL_SYSTEM_PROMPT + """

TAREFA: Análise estratégica jurídica.
Você é um sênior estrategista do escritório AFJ. Avalie o caso com objetividade:
- Identifique pontos fortes e fracos da posição do cliente
- Proponha teses principais e subsidiárias
- Estime probabilidade de êxito (baixa/média/alta — com justificativa)
- Sugira a sequência processual mais eficiente
- Identifique riscos e como mitigá-los
- Baseie TODA análise nos fatos e precedentes fornecidos."""


class StrategyAgent(BaseAgent):
    name: ClassVar[str] = "strategy_agent"
    description: ClassVar[str] = "Análise estratégica jurídica com avaliação de risco e teses"
    requires_human_approval: ClassVar[bool] = False

    async def execute(self, ctx: AgentContext) -> AgentResult:
        task = ctx.task_input
        fatos = task.get("fatos", "")
        area = task.get("area_direito", "")
        tipo_acao = task.get("tipo_acao", "")
        objetivo = task.get("objetivo", "")

        if not fatos and not tipo_acao:
            return AgentResult(
                status=AgentStatus.FAILED,
                agent_name=self.name,
                error="fatos ou tipo_acao obrigatórios para análise estratégica",
            )

        # Recuperar estratégias anteriores da memória institucional
        estrategias_anteriores = await self.recall(
            ctx,
            query=f"estratégia {area} {tipo_acao} {objetivo}",
            collections=["memorias_afj", "peticoes_afj"],
            k=5,
        )

        # Recuperar jurisprudência relevante
        juris = await self.recall(
            ctx,
            query=f"jurisprudência {area} {tipo_acao}",
            collections=["jurisprudencia"],
            k=6,
        )

        ctx_str = self._formatar_contexto(estrategias_anteriores, juris)
        taxa_exito_area, total_processos_area = await self._historico_exito_area(ctx.tenant_id, area)
        historico_str = self._formatar_historico_exito(taxa_exito_area, total_processos_area, area)

        prompt = f"""ANÁLISE ESTRATÉGICA SOLICITADA

ÁREA: {area}
TIPO DE AÇÃO: {tipo_acao}
OBJETIVO DO CLIENTE: {objetivo}

FATOS DO CASO:
{fatos or "Não informados — baseie-se no tipo de ação"}

HISTÓRICO DE ÊXITO DO ESCRITÓRIO NESTA ÁREA:
{historico_str}

CONTEXTO DISPONÍVEL:
{ctx_str}

Produza uma análise estratégica completa com:
1. Avaliação do caso (pontos fortes/fracos)
2. Teses jurídicas principais (3-5 teses)
3. Probabilidade de êxito estimada (justificada)
4. Estratégia processual recomendada
5. Riscos e mitigações
6. Documentos e provas prioritários"""

        call_start_ms = int(time.time() * 1000)
        content, input_t, output_t, cost = await call_claude(
            messages=[{"role": "user", "content": prompt}],
            system=await self.resolve_system_prompt(STRATEGY_SYSTEM),
            max_tokens=4000,
            temperature=0.4,
        )
        duration_ms = int(time.time() * 1000) - call_start_ms
        ctx.add_tokens(input_t + output_t, cost)
        ctx.add_audit_event("LLM_CALL", {
            "model": "default", "tokens": input_t + output_t,
            "cost_usd": round(cost, 4), "duration_ms": duration_ms,
        })

        # Salvar estratégia na memória institucional
        await self.remember(
            ctx,
            key=f"estrategia_{area}_{tipo_acao}",
            value={"area": area, "tipo_acao": tipo_acao, "estrategia_resumo": content[:500]},
            memory_type="SEMANTIC",
        )

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={
                "area": area,
                "tipo_acao": tipo_acao,
                "analise_estrategica": content,
                "precedentes_utilizados": len(juris),
                "estrategias_anteriores_consultadas": len(estrategias_anteriores),
                "taxa_exito_area": taxa_exito_area,
                "total_processos_area": total_processos_area,
            },
            tokens_used=input_t + output_t,
            cost_usd=cost,
        )

    async def _historico_exito_area(self, tenant_id, area: str) -> tuple[float | None, int]:
        """Fase 208.1 — taxa de êxito (EXITO+ACORDO) do próprio escritório nesta
        área, mesmo critério de `analytics_gestao` (`app/api/v1/system.py`).
        Consulta focada e isolada (não reaproveita o endpoint cacheado) — só
        este agente precisa dela."""
        if not self.db or not tenant_id or not area:
            return None, 0
        rows = (await self.db.execute(
            select(LegalProcess.desfecho, func.count(LegalProcess.id))
            .where(
                LegalProcess.tenant_id == tenant_id,
                LegalProcess.area_direito == area,
                LegalProcess.desfecho.is_not(None),
            )
            .group_by(LegalProcess.desfecho)
        )).all()
        total = sum(n for _, n in rows)
        if not total:
            return None, 0
        ganhos = sum(n for d, n in rows if d in ("EXITO", "ACORDO"))
        return round(100 * ganhos / total, 1), total

    def _formatar_historico_exito(self, taxa: float | None, total: int, area: str) -> str:
        if taxa is None:
            return f"Sem processos com desfecho registrado na área {area or 'informada'} ainda — sem histórico interno pra basear a estimativa."
        aviso = " (amostra pequena — considere com cautela)" if total < 3 else ""
        return f"{taxa}% de êxito em {total} processo(s) com desfecho registrado na área {area}{aviso}."

    def _formatar_contexto(self, estrategias: list, juris: list) -> str:
        partes = []
        if estrategias:
            partes.append("ESTRATÉGIAS ANTERIORES DO ESCRITÓRIO:")
            for e in estrategias[:3]:
                partes.append(f"  - {e.get('text', '')[:200]}")
        if juris:
            partes.append("\nJURISPRUDÊNCIA RELEVANTE:")
            for j in juris[:4]:
                p = j.get("payload", {})
                partes.append(f"  - {p.get('tribunal', 'N/A')} — {p.get('numero_processo', 'N/A')}: {j.get('text', '')[:150]}")
        return "\n".join(partes) if partes else "Nenhum contexto anterior disponível."

    async def _register_tools(self):
        return []
