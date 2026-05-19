"""
review_agent — Revisão jurídica automática em 4 etapas.

Pipeline:
  FORMAL_CHECK → LEGAL_CONSISTENCY → RISK_ASSESSMENT → STYLE_REVIEW

Toda citação não encontrada no Qdrant → [Não Verificado] → bloqueia aprovação.
"""
from typing import ClassVar
from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
from app.integrations.anthropic_client import call_claude, AFJ_LEGAL_SYSTEM_PROMPT
import structlog

log = structlog.get_logger()

REVIEW_SYSTEM_PROMPT = AFJ_LEGAL_SYSTEM_PROMPT + """

INSTRUÇÕES DE REVISÃO:
Você está revisando uma peça jurídica. Seja preciso, objetivo e construtivo.
Para cada problema encontrado, indique: localização, gravidade (ALTA/MEDIA/BAIXA) e sugestão de correção.
Nunca aceite citações de jurisprudência que não estejam na lista fornecida como verificadas."""


class ReviewAgent(BaseAgent):
    name: ClassVar[str] = "review_agent"
    description: ClassVar[str] = "Revisão jurídica automática em 4 etapas: formal, consistência, risco e estilo"
    requires_human_approval: ClassVar[bool] = False

    async def execute(self, ctx: AgentContext) -> AgentResult:
        task = ctx.task_input
        conteudo = task.get("conteudo", "")
        tipo = task.get("tipo_documento", "PETICAO")
        jurisprudencia_verificada = task.get("jurisprudencia_verificada", [])

        if not conteudo:
            return AgentResult(
                status=AgentStatus.FAILED,
                agent_name=self.name,
                error="Conteúdo do documento não fornecido para revisão",
            )

        # Recuperar legislação relevante via RAG
        legislacao = await self.recall(
            ctx,
            query=f"legislação {tipo} {task.get('area_direito', '')}",
            collections=["legislacao", "doutrina"],
            k=5,
        )

        # Executar as 4 etapas de revisão
        resultado_formal = await self._etapa_formal(conteudo, tipo)
        resultado_consistencia = await self._etapa_consistencia(conteudo, jurisprudencia_verificada, legislacao)
        resultado_risco = await self._etapa_risco(conteudo, tipo)
        resultado_estilo = await self._etapa_estilo(conteudo)

        total_tokens = (
            resultado_formal["tokens"] +
            resultado_consistencia["tokens"] +
            resultado_risco["tokens"] +
            resultado_estilo["tokens"]
        )
        total_cost = (
            resultado_formal["cost"] +
            resultado_consistencia["cost"] +
            resultado_risco["cost"] +
            resultado_estilo["cost"]
        )

        # Calcular score geral (0-100)
        score = self._calcular_score(resultado_formal, resultado_consistencia, resultado_risco, resultado_estilo)

        # Identificar bloqueadores (issues de gravidade ALTA)
        bloqueadores = [
            issue for etapa in [resultado_consistencia]
            for issue in etapa.get("issues", [])
            if issue.get("gravidade") == "ALTA"
        ]

        output = {
            "score": score,
            "pode_protocolar": score >= 70 and len(bloqueadores) == 0,
            "bloqueadores": bloqueadores,
            "etapas": {
                "formal": resultado_formal,
                "consistencia": resultado_consistencia,
                "risco": resultado_risco,
                "estilo": resultado_estilo,
            },
            "resumo": self._gerar_resumo(score, bloqueadores),
        }

        ctx.set_state("review_score", score)
        ctx.set_state("review_bloqueadores", bloqueadores)

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output=output,
            tokens_used=total_tokens,
            cost_usd=total_cost,
        )

    async def _etapa_formal(self, conteudo: str, tipo: str) -> dict:
        prompt = f"""Faça uma revisão FORMAL da peça abaixo.
Verifique: estrutura (seções obrigatórias presentes), formatação, citações de artigos (formato correto),
numeração de pedidos, endereçamento ao juízo, qualificação das partes.

DOCUMENTO ({tipo}):
{conteudo[:4000]}

Retorne um JSON com:
{{"issues": [{{"descricao": "...", "gravidade": "ALTA|MEDIA|BAIXA", "localizacao": "...", "sugestao": "..."}}],
 "aprovado": true/false, "observacoes": "..."}}"""

        content, input_t, output_t, cost = await call_claude(
            messages=[{"role": "user", "content": prompt}],
            system=REVIEW_SYSTEM_PROMPT,
            max_tokens=2000,
        )
        return {"resultado": content, "tokens": input_t + output_t, "cost": cost, "issues": []}

    async def _etapa_consistencia(self, conteudo: str, jurisprudencia: list, legislacao: list) -> dict:
        juris_str = "\n".join([f"- {j.get('numero', 'N/A')} ({j.get('tribunal', 'N/A')})" for j in jurisprudencia])
        prompt = f"""Verifique a CONSISTÊNCIA JURÍDICA da peça.
Confronte cada citação de jurisprudência com a lista de acórdãos VERIFICADOS abaixo.
Qualquer citação não listada deve ser marcada como [NÃO VERIFICADO] e é um bloqueador ALTA.

ACÓRDÃOS VERIFICADOS:
{juris_str or "Nenhum acórdão verificado disponível."}

DOCUMENTO:
{conteudo[:4000]}

Retorne JSON: {{"issues": [...], "citacoes_nao_verificadas": [...], "aprovado": true/false}}"""

        content, input_t, output_t, cost = await call_claude(
            messages=[{"role": "user", "content": prompt}],
            system=REVIEW_SYSTEM_PROMPT,
            max_tokens=2000,
        )
        return {"resultado": content, "tokens": input_t + output_t, "cost": cost, "issues": []}

    async def _etapa_risco(self, conteudo: str, tipo: str) -> dict:
        prompt = f"""Faça uma análise de RISCO da peça jurídica.
Identifique: argumentos fracos, pedidos com baixa probabilidade de êxito, ausência de teses alternativas,
riscos processuais (preclusão, intempestividade potencial, falta de provas mencionadas).

DOCUMENTO:
{conteudo[:3000]}

Retorne JSON: {{"nivel_risco": "ALTO|MEDIO|BAIXO", "riscos": [...], "teses_alternativas": [...], "pontos_fortes": [...]}}"""

        content, input_t, output_t, cost = await call_claude(
            messages=[{"role": "user", "content": prompt}],
            system=REVIEW_SYSTEM_PROMPT,
            max_tokens=2000,
        )
        return {"resultado": content, "tokens": input_t + output_t, "cost": cost}

    async def _etapa_estilo(self, conteudo: str) -> dict:
        prompt = f"""Revise o ESTILO da peça jurídica.
Verifique: adequação da linguagem (formal jurídica), clareza, concisão, redundâncias,
erros gramaticais (norma culta), uso correto de termos técnicos jurídicos em português.

DOCUMENTO (primeiros 2000 chars):
{conteudo[:2000]}

Retorne JSON: {{"issues": [...], "sugestoes_estilo": [...], "nota_redacao": 0-10}}"""

        content, input_t, output_t, cost = await call_claude(
            messages=[{"role": "user", "content": prompt}],
            system=REVIEW_SYSTEM_PROMPT,
            max_tokens=1500,
        )
        return {"resultado": content, "tokens": input_t + output_t, "cost": cost}

    def _calcular_score(self, formal, consistencia, risco, estilo) -> int:
        score = 100
        # Penalizar por bloqueadores conhecidos
        if "[NÃO VERIFICADO]" in str(consistencia.get("resultado", "")):
            score -= 30
        if "ALTA" in str(risco.get("resultado", "")):
            score -= 15
        if "issues" in formal and formal["issues"]:
            score -= len(formal["issues"]) * 5
        return max(0, min(100, score))

    def _gerar_resumo(self, score: int, bloqueadores: list) -> str:
        if score >= 90:
            return "Petição aprovada para protocolo. Excelente qualidade jurídica."
        elif score >= 70:
            return f"Petição aprovável com {len(bloqueadores)} ajuste(s) recomendado(s)."
        else:
            return f"Petição requer revisão antes do protocolo. Score: {score}/100."

    async def _register_tools(self):
        return []
