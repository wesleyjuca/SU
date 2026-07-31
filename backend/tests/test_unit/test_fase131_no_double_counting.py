"""Fase 131 — BaseAgent.run() chamava ctx.add_tokens(result.tokens_used,
result.cost_usd) de novo ao final, depois que execute() já tinha contabilizado
a mesma chamada de LLM (via ask_llm() ou o bloco manual ctx.add_tokens() da
Fase 125) — dobrando ctx.total_cost_usd, persistido como AgentRun.cost_usd e
somado direto por get_budget_status() (ai_budget.py), causando bloqueio (429)
prematuro do teto mensal de IA."""
from typing import ClassVar

import pytest

from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext


class _AskLlmAgent(BaseAgent):
    """Caminho ask_llm() — helper padronizado, já contabiliza sozinho."""
    name: ClassVar[str] = "ask_llm_stub"
    description: ClassVar[str] = "Agente de teste via ask_llm"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        content = await self.ask_llm(ctx, prompt="oi")
        return AgentResult(
            status=AgentStatus.SUCCESS, agent_name=self.name,
            output={"content": content},
            tokens_used=ctx.total_tokens, cost_usd=ctx.total_cost_usd,
        )

    async def _register_tools(self):
        return []


@pytest.mark.asyncio
async def test_run_nao_dobra_custo_via_ask_llm(monkeypatch):
    import app.integrations.anthropic_client as anthropic_client_mod

    async def fake_call_claude(messages, system, model=None, max_tokens=8096, temperature=0.3):
        return "resposta", 10, 20, 0.05

    monkeypatch.setattr(anthropic_client_mod, "call_claude", fake_call_claude)

    agent = _AskLlmAgent()
    ctx = AgentContext(task_type="test")
    result = await agent.run(ctx)

    assert result.status == AgentStatus.SUCCESS
    assert ctx.total_cost_usd == pytest.approx(0.05)  # não 0.10
    assert ctx.total_tokens == 30  # não 60
    llm_events = [e for e in ctx.audit_events if e["action"] == "LLM_CALL"]
    assert len(llm_events) == 1  # só ask_llm contabilizou, run() não gravou 2º evento


@pytest.mark.asyncio
async def test_run_nao_dobra_custo_via_call_claude_direto(monkeypatch):
    """Um dos 12 agentes instrumentados manualmente na Fase 125 (padrão
    call_claude direto + ctx.add_tokens() dentro de execute()) — petition_agent
    como representante real, não um stub sintético."""
    import app.agents.petition.petition_agent as petition_mod

    async def fake_call_claude(messages, system, max_tokens=8096, temperature=0.3):
        return "Petição gerada.", 100, 200, 0.10

    monkeypatch.setattr(petition_mod, "call_claude", fake_call_claude)

    async def _sem_citacoes(texto, tribunal=None):
        return []

    monkeypatch.setattr("app.services.citacao_check.verificar_citacoes", _sem_citacoes)

    agent = petition_mod.PetitionAgent()
    ctx = AgentContext(task_type="test", task_input={
        "tipo_peticao": "PETICAO_INICIAL",
        "processo": {"tribunal": "TJCE", "area_direito": "CIVIL"},
    })
    result = await agent.run(ctx)

    assert result.status == AgentStatus.AWAITING_APPROVAL
    assert ctx.total_cost_usd == pytest.approx(0.10)  # não 0.20
    assert ctx.total_tokens == 300  # não 600
