"""coding_agent — Geração e revisão de código para o sistema AFJ."""
import time
from typing import ClassVar
from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
from app.integrations.anthropic_client import call_claude
from app.agents.coding.repo_context import build_contexto
import structlog

log = structlog.get_logger()

CODING_SYSTEM = """Você é engenheiro de software sênior especializado em Python/FastAPI e Next.js/TypeScript.
Escreva código limpo, tipado, seguro e modular.
Sempre inclua: tipos Python completos, tratamento de erros, sem SQL injection, sem XSS.
Nunca altere produção automaticamente — apenas sugira código para revisão humana."""


class CodingAgent(BaseAgent):
    name: ClassVar[str] = "coding_agent"
    description: ClassVar[str] = "Geração e revisão de código para o sistema AFJ"
    requires_human_approval: ClassVar[bool] = True  # código nunca vai direto para produção

    async def execute(self, ctx: AgentContext) -> AgentResult:
        task = ctx.task_input
        descricao = task.get("descricao", "")
        linguagem = task.get("linguagem", "python")
        contexto_codigo = task.get("contexto_codigo", "")

        arquivos = task.get("arquivos") or []
        if arquivos:
            contexto_real = build_contexto(arquivos)
            contexto_codigo = f"{contexto_codigo}\n\n{contexto_real}".strip() if contexto_codigo else contexto_real

        if not descricao:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error="descricao obrigatória")

        prompt = f"""Gere código {linguagem} para o AFJ CORE SYSTEM:

TAREFA: {descricao}

CONTEXTO DO SISTEMA:
{contexto_codigo or "Sistema jurídico multiagente com FastAPI + Next.js + PostgreSQL + Qdrant"}

Retorne:
1. Código completo e funcional
2. Breve explicação das decisões de design
3. Como integrar ao sistema existente
4. Testes unitários sugeridos"""

        call_start_ms = int(time.time() * 1000)
        content, input_t, output_t, cost = await call_claude(
            messages=[{"role": "user", "content": prompt}],
            system=CODING_SYSTEM,
            max_tokens=4000,
            temperature=0.1,
        )
        duration_ms = int(time.time() * 1000) - call_start_ms
        ctx.add_tokens(input_t + output_t, cost)
        ctx.add_audit_event("LLM_CALL", {
            "model": "default", "tokens": input_t + output_t,
            "cost_usd": round(cost, 4), "duration_ms": duration_ms,
        })

        return AgentResult(
            status=AgentStatus.AWAITING_APPROVAL,
            agent_name=self.name,
            output={"linguagem": linguagem, "codigo_gerado": content, "descricao": descricao},
            approval_required={
                "tipo": "CODE_REVIEW",
                "titulo": f"Revisar código gerado: {descricao[:60]}",
                "descricao": "Código gerado por IA. Revise antes de incorporar ao sistema.",
            },
            tokens_used=input_t + output_t,
            cost_usd=cost,
        )

    async def _register_tools(self):
        return []
