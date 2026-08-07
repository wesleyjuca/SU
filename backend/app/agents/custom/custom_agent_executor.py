"""CustomAgentExecutor — Fase 140.2: executor genérico parametrizado por uma
linha CustomAgent (não um BaseAgent subclass por proposta). Contrato:
1 retrieve() (se rag_collections) + 1 call_claude(). ctx.task_input deve
conter custom_agent_id (obrigatório) e opcionalmente descricao/query (a
instrução do usuário para este run — o system_prompt do agente é fixo, a
tarefa em si varia por execução)."""
import time
import uuid
from typing import ClassVar

from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
from app.integrations.anthropic_client import call_claude
import structlog

log = structlog.get_logger()


class CustomAgentExecutor(BaseAgent):
    name: ClassVar[str] = "custom_agent"
    description: ClassVar[str] = "Executor genérico de agentes customizados aprovados (Fase 140.2)"
    requires_human_approval: ClassVar[bool] = False

    async def execute(self, ctx: AgentContext) -> AgentResult:
        raw_id = ctx.task_input.get("custom_agent_id")
        if not raw_id:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name,
                                error="custom_agent_id ausente em task_input.")
        try:
            agent_id = uuid.UUID(str(raw_id))
        except ValueError:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name,
                                error="custom_agent_id inválido.")

        from sqlalchemy import select
        from app.models.custom_agent import CustomAgent
        row = (await self.db.execute(select(CustomAgent).where(CustomAgent.id == agent_id))).scalar_one_or_none()
        if not row:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name,
                                error="Agente customizado não encontrado.")
        # Barreira de segurança — nem PENDENTE nem REJEITADO pode ser
        # disparado. classify_task() é síncrono e não tem acesso ao DB, não
        # pode barrar antes; esta é a ÚNICA checagem contra execução de um
        # agente não aprovado.
        if row.status != "APROVADO":
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name,
                                error=f"Agente '{row.name}' não está aprovado (status={row.status}).")

        # Cap de custo explícito — ask_llm() é código morto (não usado por
        # nenhum agente real, confirmado na Fase 140.1); como este executor
        # chama call_claude() direto (mesmo padrão dos 12 agentes reais), a
        # checagem de orçamento não vem de graça e precisa ser feita aqui.
        if ctx.total_cost_usd >= row.max_cost_usd_per_run:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name,
                                error=f"Cap de custo do agente atingido (US$ {row.max_cost_usd_per_run:.2f}).")

        query = ctx.task_input.get("descricao") or ctx.task_input.get("query") or ""
        retrieved_chunks = []
        if row.rag_collections:
            retrieved_chunks = await self.recall(ctx, query=query or row.description, collections=row.rag_collections, k=8)

        contexto_rag = ""
        if retrieved_chunks:
            contexto_rag = "\n\n--- CONTEXTO RECUPERADO ---\n" + "\n\n".join(
                c.get("text", "") for c in retrieved_chunks
            )[:20000]

        call_start_ms = int(time.time() * 1000)
        content, tokens_in, tokens_out, cost = await call_claude(
            messages=[{"role": "user", "content": (query or "Execute sua tarefa.") + contexto_rag}],
            system=row.system_prompt,
            max_tokens=4096,
        )
        duration_ms = int(time.time() * 1000) - call_start_ms
        ctx.add_tokens(tokens_in + tokens_out, cost)
        ctx.add_audit_event("LLM_CALL", {
            "model": "default", "tokens": tokens_in + tokens_out,
            "cost_usd": round(cost, 4), "duration_ms": duration_ms,
        })

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={
                "custom_agent_id": str(row.id),
                "custom_agent_name": row.name,
                "resposta": content,
                "rag_chunks_usados": len(retrieved_chunks),
            },
            tokens_used=tokens_in + tokens_out,
            cost_usd=cost,
        )
