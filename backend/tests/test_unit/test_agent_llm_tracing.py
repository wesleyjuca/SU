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
