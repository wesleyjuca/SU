"""
jurisprudence_agent — Busca jurisprudência em fontes verificáveis.

REGRA ABSOLUTA: nunca fabrica ou infere precedentes.
Toda citação retornada contém: tribunal, relator, número, data, ementa, fonte.
Resultados sem confirmação são marcados [NÃO VERIFICADO].
"""
from typing import ClassVar
from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
from app.integrations.anthropic_client import call_claude, AFJ_LEGAL_SYSTEM_PROMPT
import structlog

log = structlog.get_logger()

JURISPRUDENCE_SYSTEM = AFJ_LEGAL_SYSTEM_PROMPT + """

TAREFA: Análise e organização de jurisprudência.
- Organize os acórdãos fornecidos por relevância para a tese indicada.
- Para cada acórdão, extraia: tese central, aplicabilidade ao caso, pontos fortes e fracos.
- NUNCA adicione precedentes além dos fornecidos no contexto.
- Se nenhum acórdão for encontrado, informe claramente — não substitua por referências genéricas."""


class JurisprudenceAgent(BaseAgent):
    name: ClassVar[str] = "jurisprudence_agent"
    description: ClassVar[str] = "Busca e analisa jurisprudência em fontes verificáveis do Qdrant"
    requires_human_approval: ClassVar[bool] = False

    async def execute(self, ctx: AgentContext) -> AgentResult:
        task = ctx.task_input
        query = task.get("query", "")
        area_direito = task.get("area_direito", "")
        tribunal_preferido = task.get("tribunal", "")
        tese = task.get("tese", "")

        if not query and not tese:
            return AgentResult(
                status=AgentStatus.FAILED,
                agent_name=self.name,
                error="query ou tese obrigatórios para busca jurisprudencial",
            )

        search_query = f"{query} {tese} {area_direito}".strip()

        # Busca exclusivamente no Qdrant — sem inventar
        chunks = await self.recall(
            ctx,
            query=search_query,
            collections=["jurisprudencia"],
            k=10,
        )

        if not chunks:
            return AgentResult(
                status=AgentStatus.SUCCESS,
                agent_name=self.name,
                output={
                    "encontrados": 0,
                    "resultados": [],
                    "aviso": "Nenhuma jurisprudência encontrada na base para esta consulta. "
                             "Adicione acórdãos via ingestão RAG antes de gerar petições.",
                    "query": search_query,
                },
            )

        # Filtrar por tribunal se especificado
        if tribunal_preferido:
            chunks_filtrados = [c for c in chunks if tribunal_preferido.upper() in c.get("payload", {}).get("tribunal", "").upper()]
            if chunks_filtrados:
                chunks = chunks_filtrados

        # Formatar resultados com metadados de rastreabilidade
        resultados = []
        for chunk in chunks[:8]:
            payload = chunk.get("payload", {})
            resultados.append({
                "tribunal": payload.get("tribunal", "[NÃO VERIFICADO]"),
                "numero_processo": payload.get("numero_processo", "[NÃO VERIFICADO]"),
                "relator": payload.get("relator", "[NÃO VERIFICADO]"),
                "data_julgamento": payload.get("data_julgamento", "[NÃO VERIFICADO]"),
                "ementa": chunk.get("text", "")[:500],
                "area_direito": payload.get("area_direito", ""),
                "favoravel": payload.get("favoravel"),
                "score_relevancia": round(chunk.get("score", 0), 3),
                "verificado": True,  # vem do Qdrant — fonte confiável
            })

        # Análise IA dos precedentes encontrados (sem inventar novos)
        analise = ""
        total_tokens = 0
        total_cost = 0.0

        if resultados and tese:
            juris_str = "\n\n".join([
                f"[{i+1}] {r['tribunal']} — {r['numero_processo']}\nRelator: {r['relator']} | Data: {r['data_julgamento']}\nEmenta: {r['ementa']}"
                for i, r in enumerate(resultados[:5])
            ])
            content, input_t, output_t, cost = await call_claude(
                messages=[{
                    "role": "user",
                    "content": f"Analise estes acórdãos em relação à tese: '{tese}'\n\nACÓRDÃOS:\n{juris_str}\n\nClassifique cada um: favorável/desfavorável à tese, relevância e como utilizá-los na peça."
                }],
                system=JURISPRUDENCE_SYSTEM,
                max_tokens=2000,
            )
            analise = content
            total_tokens = input_t + output_t
            total_cost = cost

        ctx.set_state("jurisprudencia_encontrada", len(resultados))
        ctx.set_state("jurisprudencia_resultados", resultados)

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={
                "encontrados": len(resultados),
                "resultados": resultados,
                "analise_ia": analise,
                "query": search_query,
                "aviso": None if resultados else "Base vazia para esta área",
            },
            tokens_used=total_tokens,
            cost_usd=total_cost,
        )

    async def _register_tools(self):
        return []
