"""visual_law_agent — Gera fluxogramas, timelines e resumos visuais jurídicos."""
import time
from typing import ClassVar
from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
from app.integrations.anthropic_client import call_claude
import structlog

log = structlog.get_logger()

VISUAL_SYSTEM = """Você é especialista em Visual Law para escritórios de advocacia brasileiros.
Gere representações visuais claras e profissionais no formato solicitado.
Use linguagem simples e acessível ao cliente, sem jargão excessivo.
Para Mermaid: siga a sintaxe exata do Mermaid.js."""

_DIAGRAM_KEYWORDS = ("flowchart", "graph", "sequencediagram", "classdiagram",
                     "timeline", "gantt", "erdiagram", "statediagram", "journey", "pie")


def _strip_fences(texto: str) -> str:
    t = texto.strip()
    if t.startswith("```"):
        linhas = t.splitlines()[1:]
        if linhas and linhas[-1].strip().startswith("```"):
            linhas = linhas[:-1]
        t = "\n".join(linhas).strip()
    return t


class VisualLawAgent(BaseAgent):
    name: ClassVar[str] = "visual_law_agent"
    description: ClassVar[str] = "Gera fluxogramas Mermaid, timelines e diagramas jurídicos"
    requires_human_approval: ClassVar[bool] = False
    strict_validation: ClassVar[bool] = True

    async def validate(self, ctx: AgentContext, result: AgentResult) -> list[str]:
        issues: list[str] = []
        if result.status != AgentStatus.SUCCESS:
            return issues
        formato = result.output.get("formato")
        if formato == "mermaid":
            texto = _strip_fences(result.output.get("mermaid", ""))
            if not texto:
                return ["Diagrama Mermaid vazio."]
            primeira_linha = texto.splitlines()[0].strip().lower()
            if not any(primeira_linha.startswith(kw) for kw in _DIAGRAM_KEYWORDS):
                issues.append(f"Diagrama não inicia com tipo Mermaid reconhecido: '{primeira_linha[:30]}'")
            abertos = texto.count("[") + texto.count("(") + texto.count("{")
            fechados = texto.count("]") + texto.count(")") + texto.count("}")
            if abertos != fechados:
                issues.append(f"Colchetes/parênteses/chaves desbalanceados ({abertos} vs {fechados}) — possível truncamento.")
            if len(texto) < 15:
                issues.append("Conteúdo Mermaid suspeito de truncamento (muito curto).")
        elif formato == "markdown":
            texto = result.output.get("markdown", "")
            if not texto.strip() or "|" not in texto:
                issues.append("Quadro comparativo não parece conter tabela Markdown válida.")
        return issues

    async def execute(self, ctx: AgentContext) -> AgentResult:
        task = ctx.task_input
        tipo = task.get("tipo", "fluxograma")   # fluxograma, timeline, quadro_comparativo
        conteudo = task.get("conteudo", "")
        titulo = task.get("titulo", "Diagrama Jurídico")

        if not conteudo:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error="conteudo obrigatório")

        if tipo == "fluxograma":
            return await self._gerar_fluxograma(ctx, titulo, conteudo)
        elif tipo == "timeline":
            return await self._gerar_timeline(ctx, titulo, conteudo)
        elif tipo == "quadro_comparativo":
            return await self._gerar_quadro(ctx, titulo, conteudo)
        else:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error=f"Tipo desconhecido: {tipo}")

    async def _gerar_fluxograma(self, ctx: AgentContext, titulo: str, conteudo: str) -> AgentResult:
        prompt = f"""Gere um fluxograma Mermaid para representar visualmente:

TÍTULO: {titulo}
CONTEÚDO: {conteudo}

Retorne APENAS o código Mermaid válido, começando com 'flowchart TD' ou 'graph TD'.
Use nós com descrições em português, curtos (máx 30 chars por nó).
Inclua cores: verde para aprovações, vermelho para rejeições, amarelo para aguardando."""

        call_start_ms = int(time.time() * 1000)
        content, input_t, output_t, cost = await call_claude(
            messages=[{"role": "user", "content": prompt}],
            system=VISUAL_SYSTEM,
            max_tokens=1500,
        )
        duration_ms = int(time.time() * 1000) - call_start_ms
        ctx.add_tokens(input_t + output_t, cost)
        ctx.add_audit_event("LLM_CALL", {
            "model": "default", "tokens": input_t + output_t,
            "cost_usd": round(cost, 4), "duration_ms": duration_ms,
        })

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={"tipo": "fluxograma", "titulo": titulo, "mermaid": content, "formato": "mermaid"},
            tokens_used=input_t + output_t,
            cost_usd=cost,
        )

    async def _gerar_timeline(self, ctx: AgentContext, titulo: str, conteudo: str) -> AgentResult:
        prompt = f"""Gere uma timeline Mermaid para os eventos jurídicos:

TÍTULO: {titulo}
EVENTOS: {conteudo}

Retorne APENAS código Mermaid válido com 'timeline' como primeiro token.
Formato: timeline
  title {titulo}
  section Fase
    Evento : data"""

        call_start_ms = int(time.time() * 1000)
        content, input_t, output_t, cost = await call_claude(
            messages=[{"role": "user", "content": prompt}],
            system=VISUAL_SYSTEM,
            max_tokens=1000,
        )
        duration_ms = int(time.time() * 1000) - call_start_ms
        ctx.add_tokens(input_t + output_t, cost)
        ctx.add_audit_event("LLM_CALL", {
            "model": "default", "tokens": input_t + output_t,
            "cost_usd": round(cost, 4), "duration_ms": duration_ms,
        })

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={"tipo": "timeline", "titulo": titulo, "mermaid": content, "formato": "mermaid"},
            tokens_used=input_t + output_t,
            cost_usd=cost,
        )

    async def _gerar_quadro(self, ctx: AgentContext, titulo: str, conteudo: str) -> AgentResult:
        prompt = f"""Gere um quadro comparativo em Markdown para:

TÍTULO: {titulo}
ITENS PARA COMPARAR: {conteudo}

Retorne uma tabela Markdown com colunas relevantes. Use ✅ e ❌ para facilitarvisiulização."""

        call_start_ms = int(time.time() * 1000)
        content, input_t, output_t, cost = await call_claude(
            messages=[{"role": "user", "content": prompt}],
            system=VISUAL_SYSTEM,
            max_tokens=800,
        )
        duration_ms = int(time.time() * 1000) - call_start_ms
        ctx.add_tokens(input_t + output_t, cost)
        ctx.add_audit_event("LLM_CALL", {
            "model": "default", "tokens": input_t + output_t,
            "cost_usd": round(cost, 4), "duration_ms": duration_ms,
        })

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={"tipo": "quadro_comparativo", "titulo": titulo, "markdown": content, "formato": "markdown"},
            tokens_used=input_t + output_t,
            cost_usd=cost,
        )

    async def _register_tools(self):
        return []
