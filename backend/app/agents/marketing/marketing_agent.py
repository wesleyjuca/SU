"""marketing_agent — Geração de conteúdo para captação e campanhas jurídicas."""
from typing import ClassVar
from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
from app.integrations.anthropic_client import call_claude
import structlog

log = structlog.get_logger()

MARKETING_SYSTEM = """Você é especialista em marketing jurídico para escritórios de advocacia brasileiros.
Crie conteúdo profissional, educativo e que demonstre autoridade sem prometer resultados.
Respeite as normas do CFOAB (Código de Ética e Disciplina da OAB):
- Não prometa resultados ou vitórias
- Não use linguagem sensacionalista
- Foque em educação jurídica e expertise
- Tom: profissional, acessível, confiável"""


class MarketingAgent(BaseAgent):
    name: ClassVar[str] = "marketing_agent"
    description: ClassVar[str] = "Conteúdo para redes sociais, posts educativos e campanhas jurídicas"
    requires_human_approval: ClassVar[bool] = True  # conteúdo publicado requer revisão

    async def execute(self, ctx: AgentContext) -> AgentResult:
        task = ctx.task_input
        tipo = task.get("tipo", "post_instagram")  # post_instagram, reels_roteiro, artigo_linkedin
        tema = task.get("tema", "")
        area = task.get("area_direito", "")

        if not tema:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error="tema obrigatório")

        if tipo == "post_instagram":
            return await self._post_instagram(ctx, tema, area)
        elif tipo == "reels_roteiro":
            return await self._roteiro_reels(ctx, tema, area)
        elif tipo == "artigo_linkedin":
            return await self._artigo_linkedin(ctx, tema, area)
        else:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error=f"Tipo: {tipo}")

    async def _post_instagram(self, ctx: AgentContext, tema: str, area: str) -> AgentResult:
        prompt = f"""Crie um post para o Instagram do escritório AFJ Advogados sobre:
Tema: {tema}
Área: {area}

Formato:
- Gancho forte na primeira linha (sem cortar)
- 3-5 linhas educativas
- Call-to-action sutil
- 8-10 hashtags relevantes
- Máximo 2200 caracteres
- Tom educativo, não comercial"""

        content, input_t, output_t, cost = await call_claude(
            messages=[{"role": "user", "content": prompt}],
            system=MARKETING_SYSTEM,
            max_tokens=800,
        )
        return AgentResult(
            status=AgentStatus.AWAITING_APPROVAL,
            agent_name=self.name,
            output={"tipo": "post_instagram", "conteudo": content, "tema": tema},
            approval_required={"tipo": "MARKETING_CONTENT", "titulo": f"Revisar post Instagram: {tema}", "descricao": "Post gerado por IA para Instagram. Revise antes de publicar."},
            tokens_used=input_t + output_t,
            cost_usd=cost,
        )

    async def _roteiro_reels(self, ctx: AgentContext, tema: str, area: str) -> AgentResult:
        prompt = f"""Crie um roteiro de Reels (60s) sobre {tema} para o AFJ Advogados.
Formato: Cena por cena com narração e sugestão de visual.
Regras OAB: educativo, sem prometer resultados."""

        content, input_t, output_t, cost = await call_claude(
            messages=[{"role": "user", "content": prompt}],
            system=MARKETING_SYSTEM,
            max_tokens=800,
        )
        return AgentResult(
            status=AgentStatus.AWAITING_APPROVAL,
            agent_name=self.name,
            output={"tipo": "reels_roteiro", "conteudo": content, "tema": tema},
            approval_required={"tipo": "MARKETING_CONTENT", "titulo": f"Revisar roteiro Reels: {tema}", "descricao": "Roteiro gerado. Revise antes de gravar."},
            tokens_used=input_t + output_t,
            cost_usd=cost,
        )

    async def _artigo_linkedin(self, ctx: AgentContext, tema: str, area: str) -> AgentResult:
        prompt = f"""Escreva um artigo LinkedIn completo sobre {tema} ({area}).
Extensão: 600-900 palavras. Tom: autoridade técnica, acessível.
Estrutura: introdução impactante, desenvolvimento com subtítulos, conclusão com reflexão."""

        content, input_t, output_t, cost = await call_claude(
            messages=[{"role": "user", "content": prompt}],
            system=MARKETING_SYSTEM,
            max_tokens=1500,
        )
        return AgentResult(
            status=AgentStatus.AWAITING_APPROVAL,
            agent_name=self.name,
            output={"tipo": "artigo_linkedin", "conteudo": content, "tema": tema},
            approval_required={"tipo": "MARKETING_CONTENT", "titulo": f"Revisar artigo LinkedIn: {tema}", "descricao": "Artigo gerado. Revise e assine antes de publicar."},
            tokens_used=input_t + output_t,
            cost_usd=cost,
        )

    async def _register_tools(self):
        return []
