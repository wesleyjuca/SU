"""Fase 113 — tracing por chamada de LLM dentro de um AgentRun.
`ctx.audit_events` já existia (AGENT_START/AGENT_VALIDATION/AGENT_COMPLETE)
mas nunca era lido/persistido. Agora ask_llm() grava um evento LLM_CALL
por chamada, e agent_tasks.py persiste ctx.audit_events em output["_trace"]."""
import asyncio
import time
from typing import ClassVar

import pytest

from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext


class _StubAgent(BaseAgent):
    name: ClassVar[str] = "stub_agent"
    description: ClassVar[str] = "Agente de teste"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        content = await self.ask_llm(ctx, prompt="oi")
        return AgentResult(status=AgentStatus.SUCCESS, agent_name=self.name, output={"content": content})

    async def _register_tools(self):
        return []


@pytest.mark.asyncio
async def test_ask_llm_grava_evento_llm_call_com_duracao(monkeypatch):
    async def fake_call_claude(messages, system, model=None, max_tokens=8096, temperature=0.3):
        await asyncio.sleep(0.02)
        return "resposta", 10, 20, 0.01

    # ask_llm importa call_claude localmente de app.integrations.anthropic_client —
    # o monkeypatch precisa mirar o módulo real de onde a função é lida a cada chamada.
    import app.integrations.anthropic_client as anthropic_client_mod
    monkeypatch.setattr(anthropic_client_mod, "call_claude", fake_call_claude)

    agent = _StubAgent()
    ctx = AgentContext(task_type="test")

    t0 = time.monotonic()
    content = await agent.ask_llm(ctx, prompt="oi")
    duracao_real = (time.monotonic() - t0) * 1000

    assert content == "resposta"
    llm_events = [e for e in ctx.audit_events if e["action"] == "LLM_CALL"]
    assert len(llm_events) == 1
    evento = llm_events[0]
    assert evento["details"]["tokens"] == 30
    assert evento["details"]["cost_usd"] == 0.01
    assert evento["details"]["duration_ms"] >= 15  # sleep de 20ms, alguma folga
    assert evento["details"]["duration_ms"] <= duracao_real + 50
    assert "timestamp" in evento  # add_audit_event já grava isso automaticamente


@pytest.mark.asyncio
async def test_execute_via_run_acumula_trace_completo(monkeypatch):
    import app.integrations.anthropic_client as anthropic_client_mod

    async def fake_call_claude(messages, system, model=None, max_tokens=8096, temperature=0.3):
        return "ok", 5, 5, 0.001

    monkeypatch.setattr(anthropic_client_mod, "call_claude", fake_call_claude)

    agent = _StubAgent()
    ctx = AgentContext(task_type="test")
    result = await agent.run(ctx)

    assert result.status == AgentStatus.SUCCESS
    acoes = [e["action"] for e in ctx.audit_events]
    assert acoes == ["AGENT_START", "LLM_CALL", "AGENT_COMPLETE"]


def test_output_trace_e_o_mesmo_ctx_audit_events():
    """Simula exatamente a linha adicionada em agent_tasks.py::_run_async —
    output['_trace'] = ctx.audit_events — sem precisar montar Celery/LangGraph."""
    ctx = AgentContext(task_type="test")
    ctx.add_audit_event("AGENT_START", {"agent": "x"})
    ctx.add_audit_event("LLM_CALL", {"tokens": 100, "duration_ms": 500})

    output = {"resumo": "tudo certo"}
    output["_trace"] = ctx.audit_events

    assert output["_trace"] == ctx.audit_events
    assert len(output["_trace"]) == 2
    assert output["_trace"][1]["action"] == "LLM_CALL"
    assert output["resumo"] == "tudo certo"  # dado original preservado


# ─── Fase 125 — agentes que bypassam ask_llm (call_claude direto) ──────────
# Cada um desses módulos importa `call_claude` no nível do módulo
# (`from app.integrations.anthropic_client import call_claude`), diferente
# de ask_llm() que importa localmente a cada chamada — por isso o monkeypatch
# aqui precisa mirar o nome dentro do módulo do agente, não anthropic_client.


@pytest.mark.asyncio
async def test_strategy_agent_grava_llm_call_trivial(monkeypatch):
    """Padrão trivial: 1 call site direto em execute(), ctx já em escopo."""
    import app.agents.strategy.strategy_agent as strategy_mod

    async def fake_call_claude(messages, system, model=None, max_tokens=8096, temperature=0.3):
        return "estratégia gerada", 50, 100, 0.02

    monkeypatch.setattr(strategy_mod, "call_claude", fake_call_claude)

    agent = strategy_mod.StrategyAgent()
    ctx = AgentContext(task_type="test", task_input={"area": "civel", "tipo_acao": "cobranca"})
    result = await agent.execute(ctx)

    assert result.status == AgentStatus.SUCCESS
    llm_events = [e for e in ctx.audit_events if e["action"] == "LLM_CALL"]
    assert len(llm_events) == 1
    assert llm_events[0]["details"]["tokens"] == 150
    assert llm_events[0]["details"]["cost_usd"] == 0.02
    assert ctx.total_tokens == 150
    assert ctx.total_cost_usd == 0.02


@pytest.mark.asyncio
async def test_review_agent_4_etapas_geram_4_eventos_llm_call(monkeypatch):
    """Padrão estrutural: ctx precisou ser thread-ado pros 4 helpers
    _etapa_formal/_etapa_consistencia/_etapa_risco/_etapa_estilo — confirma
    que cada um grava seu próprio evento (4 chamadas paralelas via gather)."""
    import app.agents.review.review_agent as review_mod

    chamadas = 0

    async def fake_call_claude(messages, system, model=None, max_tokens=8096, temperature=0.3):
        nonlocal chamadas
        chamadas += 1
        return '{"issues": [], "aprovado": true}', 10, 10, 0.001

    monkeypatch.setattr(review_mod, "call_claude", fake_call_claude)

    agent = review_mod.ReviewAgent()
    ctx = AgentContext(task_type="test")

    system_prompt = review_mod.REVIEW_SYSTEM_PROMPT

    r_formal = await agent._etapa_formal(ctx, "conteúdo de teste", "PETICAO_INICIAL", system_prompt)
    r_consistencia = await agent._etapa_consistencia(ctx, "conteúdo de teste", [], [], system_prompt)
    r_risco = await agent._etapa_risco(ctx, "conteúdo de teste", "PETICAO_INICIAL", system_prompt)
    r_estilo = await agent._etapa_estilo(ctx, "conteúdo de teste", system_prompt)

    assert chamadas == 4
    assert all(r["tokens"] == 20 for r in (r_formal, r_consistencia, r_risco, r_estilo))
    llm_events = [e for e in ctx.audit_events if e["action"] == "LLM_CALL"]
    assert len(llm_events) == 4
    assert ctx.total_tokens == 80  # 4 × 20
    assert ctx.total_cost_usd == pytest.approx(0.004)  # 4 × 0.001


@pytest.mark.asyncio
async def test_process_agent_gera_1_evento_llm_call_por_movimento(monkeypatch):
    """Padrão estrutural: _resumir_movimento não recebia ctx — agora recebe.
    Roda em loop no polling real (_poll_single_process), então cada movimento
    resumido deve gerar seu próprio evento (granularidade intencional)."""
    import app.agents.process.process_agent as process_mod

    async def fake_call_claude(messages, system, model=None, max_tokens=8096, temperature=0.3):
        return "resumo do andamento", 15, 25, 0.003

    monkeypatch.setattr(process_mod, "call_claude", fake_call_claude)

    agent = process_mod.ProcessAgent()
    ctx = AgentContext(task_type="test")

    descricao_longa = "Andamento processual detalhado " * 5  # > 50 chars
    for _ in range(3):
        content, tokens, _, cost = await agent._resumir_movimento(ctx, {"descricao": descricao_longa})
        assert content == "resumo do andamento"
        assert tokens == 40
        assert cost == 0.003

    llm_events = [e for e in ctx.audit_events if e["action"] == "LLM_CALL"]
    assert len(llm_events) == 3
    assert ctx.total_tokens == 120  # 3 × 40

    # descrição curta (<50 chars) não chama call_claude nem gera evento
    content_curto, tokens_curto, _, cost_curto = await agent._resumir_movimento(ctx, {"descricao": "curto"})
    assert (content_curto, tokens_curto, cost_curto) == ("curto", 0, 0.0)
    assert len([e for e in ctx.audit_events if e["action"] == "LLM_CALL"]) == 3  # inalterado


@pytest.mark.asyncio
async def test_innovation_agent_nao_descarta_mais_tokens_e_custo(monkeypatch):
    """Regressão do bug encontrado junto com o mapeamento desta fase:
    _gerar_proposta descartava tokens/custo (`content, _, _, _ = ...`) e
    execute() nunca setava tokens_used/cost_usd no AgentResult — agente
    reportava custo zero sempre, mesmo gastando IA de verdade."""
    import app.agents.innovation.innovation_agent as innovation_mod

    async def fake_call_claude(messages, system, model=None, max_tokens=8096, temperature=0.3):
        return "proposta de melhoria", 80, 200, 0.05

    monkeypatch.setattr(innovation_mod, "call_claude", fake_call_claude)

    agent = innovation_mod.InnovationAgent()
    ctx = AgentContext(task_type="test", task_input={"foco": "geral"})
    result = await agent.execute(ctx)

    assert result.status == AgentStatus.SUCCESS
    assert result.tokens_used == 280
    assert result.cost_usd == 0.05
    llm_events = [e for e in ctx.audit_events if e["action"] == "LLM_CALL"]
    assert len(llm_events) == 1
    assert llm_events[0]["details"]["tokens"] == 280
    assert llm_events[0]["details"]["cost_usd"] == 0.05
