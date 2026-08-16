"""Fase 196 — resposta de IA em streaming nos agentes (débito técnico G).
`ask_llm()` continua devolvendo só o texto pronto (mesmo contrato) mas, com
`ctx.stream_enabled=True` e `ctx.triggered_by` setado, passa a chamar
`call_llm_stream` em vez de `call_claude` e publica cada pedaço via
WebSocket (evento AGENT_RUN_DELTA) conforme chega — escopo restrito a
disparo direto (chain de 1 passo), setado por `execute_chain_step` em
orchestrator.py."""
import uuid
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


async def _fake_call_llm_stream(messages, system, model=None, max_tokens=8096, temperature=0.3):
    yield ("delta", "Olá, ")
    yield ("delta", "tudo bem?")
    yield ("done", {"input_tokens": 12, "output_tokens": 7, "cost_usd": 0.002})


@pytest.mark.asyncio
async def test_stream_enabled_usa_call_llm_stream_e_acumula_conteudo(monkeypatch):
    import app.integrations.llm_client as llm_client_mod
    monkeypatch.setattr(llm_client_mod, "call_llm_stream", _fake_call_llm_stream)

    publicados = []

    async def fake_publish_event(user_id, event_type, data):
        publicados.append((user_id, event_type, data))

    import app.api.v1.ws as ws_mod
    monkeypatch.setattr(ws_mod, "publish_event", fake_publish_event)

    triggered_by = uuid.uuid4()
    run_id = uuid.uuid4()
    ctx = AgentContext(task_type="test", triggered_by=triggered_by, run_id=run_id, stream_enabled=True)

    agent = _StubAgent()
    content = await agent.ask_llm(ctx, prompt="oi")

    assert content == "Olá, tudo bem?"
    assert ctx.total_tokens == 19
    assert ctx.total_cost_usd == pytest.approx(0.002)

    deltas = [d for (_, tipo, d) in publicados if tipo == "AGENT_RUN_DELTA"]
    assert len(deltas) == 2
    assert deltas[0]["delta"] == "Olá, "
    assert deltas[1]["delta"] == "tudo bem?"
    assert all(d["run_id"] == str(run_id) for d in deltas)
    assert all(d["agent_name"] == "stub_agent" for d in deltas)
    assert all(uid == str(triggered_by) for (uid, _, _) in publicados)


@pytest.mark.asyncio
async def test_sem_triggered_by_nao_streama_mesmo_com_stream_enabled(monkeypatch):
    """Sem usuário disparador não há pra quem publicar — cai no caminho
    normal (call_claude), nunca tenta streamar (ex.: polling automático,
    triggered_by=None)."""
    async def fake_call_claude(messages, system, model=None, max_tokens=8096, temperature=0.3):
        return "resposta normal", 3, 4, 0.001

    import app.integrations.anthropic_client as anthropic_client_mod
    monkeypatch.setattr(anthropic_client_mod, "call_claude", fake_call_claude)

    async def _explode(*a, **k):
        raise AssertionError("call_llm_stream não deveria ser chamado sem triggered_by")
    import app.integrations.llm_client as llm_client_mod
    monkeypatch.setattr(llm_client_mod, "call_llm_stream", _explode)

    ctx = AgentContext(task_type="test", triggered_by=None, stream_enabled=True)
    agent = _StubAgent()
    content = await agent.ask_llm(ctx, prompt="oi")

    assert content == "resposta normal"


@pytest.mark.asyncio
async def test_stream_disabled_usa_caminho_normal_mesmo_com_triggered_by(monkeypatch):
    """Chain multi-passo (stream_enabled=False, setado por execute_chain_step
    quando len(chain) > 1) nunca streama, mesmo tendo triggered_by."""
    async def fake_call_claude(messages, system, model=None, max_tokens=8096, temperature=0.3):
        return "resposta da chain", 1, 1, 0.0001

    import app.integrations.anthropic_client as anthropic_client_mod
    monkeypatch.setattr(anthropic_client_mod, "call_claude", fake_call_claude)

    async def _explode(*a, **k):
        raise AssertionError("call_llm_stream não deveria ser chamado com stream_enabled=False")
    import app.integrations.llm_client as llm_client_mod
    monkeypatch.setattr(llm_client_mod, "call_llm_stream", _explode)

    ctx = AgentContext(task_type="test", triggered_by=uuid.uuid4(), stream_enabled=False)
    agent = _StubAgent()
    content = await agent.ask_llm(ctx, prompt="oi")

    assert content == "resposta da chain"


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def add(self, obj):
        pass

    async def commit(self):
        pass

    async def rollback(self):
        pass


@pytest.mark.asyncio
async def test_execute_chain_step_so_ativa_stream_pra_chain_de_1_passo(monkeypatch):
    """Roda o loop real do orquestrador (mesmo harness da Fase 169.1,
    test_agent_chaining.py) pra confirmar que quem decide `stream_enabled`
    é `execute_chain_step`, não algo que cada agente precise setar sozinho:
    disparo direto (1 passo) liga, chain multi-passo desliga."""
    import app.agents.brain.orchestrator as orch
    import app.db.base as dbbase
    import app.db.redis as dbredis

    monkeypatch.setattr(dbbase, "AsyncSessionLocal", lambda: _FakeSession())

    async def _fake_redis():
        return None
    monkeypatch.setattr(dbredis, "get_redis", _fake_redis)

    stream_flags_observados = []

    def _fake_resolve(route):
        class FakeAgent:
            name = route

            def __init__(self, db=None, redis=None, qdrant=None):
                pass

            async def run(self, ctx):
                stream_flags_observados.append(ctx.stream_enabled)
                return AgentResult(status=AgentStatus.SUCCESS, agent_name=route, output={})
        return FakeAgent
    monkeypatch.setattr(orch, "resolve_agent_class", _fake_resolve)

    # Disparo direto (get_chain("generate_petition") == ["petition_agent"]).
    ctx_direto = AgentContext(task_type="generate_petition", triggered_by=uuid.uuid4())
    await orch.execute_chain_step(ctx_direto, ["petition_agent"], 0)
    assert stream_flags_observados == [True]

    # Chain multi-passo (get_chain("new_process_intake") tem 4 passos).
    chain = ["process_agent", "jurisprudence_agent", "strategy_agent", "crm_agent"]
    ctx_chain = AgentContext(task_type="new_process_intake", triggered_by=uuid.uuid4())
    await orch.execute_chain_step(ctx_chain, chain, 0)
    assert stream_flags_observados == [True, False]
