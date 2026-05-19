"""contract_agent — Geração e análise de contratos. Requer aprovação humana."""
from typing import ClassVar
from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
from app.integrations.anthropic_client import call_claude, AFJ_LEGAL_SYSTEM_PROMPT
import structlog, uuid

log = structlog.get_logger()

CONTRACT_SYSTEM = AFJ_LEGAL_SYSTEM_PROMPT + """
TAREFA: Geração de contratos jurídicos.
- Use linguagem clara e tecnicamente precisa
- Inclua: objeto, obrigações das partes, honorários, prazo, foro, rescisão
- Nunca omita cláusulas de proteção ao escritório
- Formato: estrutura numerada com títulos em maiúsculas"""


class ContractAgent(BaseAgent):
    name: ClassVar[str] = "contract_agent"
    description: ClassVar[str] = "Geração e análise de contratos jurídicos com aprovação obrigatória"
    requires_human_approval: ClassVar[bool] = True

    async def execute(self, ctx: AgentContext) -> AgentResult:
        task = ctx.task_input
        tipo = task.get("tipo_contrato", "HONORARIOS")
        dados = task.get("dados", {})

        templates_similares = await self.recall(ctx, query=f"contrato {tipo}", collections=["peticoes_afj"], k=3)

        prompt = f"""Gere um contrato de {tipo.replace('_', ' ').title()} para o escritório AFJ Advogados.

DADOS:
{chr(10).join(f'- {k}: {v}' for k, v in dados.items() if v)}

Cláusulas obrigatórias: objeto, qualificação das partes, honorários e forma de pagamento,
prazo de vigência, obrigações do escritório, obrigações do cliente, hipóteses de rescisão,
confidencialidade, foro de eleição (Fortaleza/CE).

Use linguagem jurídica clara e proteja os interesses do escritório."""

        content, input_t, output_t, cost = await call_claude(
            messages=[{"role": "user", "content": prompt}],
            system=CONTRACT_SYSTEM,
            max_tokens=4000,
            temperature=0.1,
        )

        doc_id = str(uuid.uuid4())
        if self.db:
            from app.models.document import Document, Contract as ContractModel
            from decimal import Decimal
            doc = Document(
                id=uuid.UUID(doc_id),
                client_id=ctx.client_id,
                tipo="CONTRATO",
                titulo=f"Contrato de {tipo.replace('_', ' ').title()}",
                conteudo_texto=content,
                status="RASCUNHO",
                gerado_por_ia=True,
                agent_run_id=ctx.run_id,
            )
            self.db.add(doc)
            contrato = ContractModel(
                document_id=uuid.UUID(doc_id),
                client_id=ctx.client_id,
                tipo=tipo,
                valor_total=Decimal(str(dados.get("valor_honorarios", 0) or 0)),
                status="RASCUNHO",
            )
            self.db.add(contrato)
            await self.db.flush()

        return AgentResult(
            status=AgentStatus.AWAITING_APPROVAL,
            agent_name=self.name,
            output={"document_id": doc_id, "tipo": tipo, "conteudo": content},
            approval_required={
                "tipo": "CONTRACT_REVIEW",
                "titulo": f"Revisar contrato de {tipo.replace('_', ' ').title()}",
                "descricao": "Contrato gerado por IA. Verifique todos os valores e cláusulas antes de enviar ao cliente.",
                "document_id": doc_id,
            },
            tokens_used=input_t + output_t,
            cost_usd=cost,
        )

    async def _register_tools(self):
        return []
